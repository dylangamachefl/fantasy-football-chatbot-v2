import { PROMPTS } from './prompts';
import { initRAG, retrieveExamples } from './rag';

// Types
type Message = { role: 'user' | 'assistant' | 'system', content: string };
type AgentState = {
  status: 'idle' | 'initializing' | 'thinking' | 'querying' | 'executing' | 'reflecting' | 'answering' | 'error';
  thoughts: string[];
  error?: string;
};

// Worker Interfaces
const dbWorker = new Worker(new URL('../workers/db.worker.ts', import.meta.url), { type: 'module' });
const llmWorker = new Worker(new URL('../workers/llm.worker.ts', import.meta.url), { type: 'module' });

// Helper to wrap Worker messaging in Promises
function workerRequest(worker: Worker, type: string, payload: any = {}): Promise<any> {
  return new Promise((resolve, reject) => {
    const id = Math.random().toString(36).substring(7);

    const handler = (e: MessageEvent) => {
      if (e.data.id === id) {
        worker.removeEventListener('message', handler);
        if (e.data.type === 'ERROR') reject(new Error(e.data.error));
        else resolve(e.data.payload);
      }
    };

    worker.addEventListener('message', handler);
    worker.postMessage({ type, payload, id });
  });
}

// Global Schema Cache
let schemaStr = "";

export class Agent {
  private onStateChange: (state: AgentState) => void;
  private state: AgentState = { status: 'idle', thoughts: [] };

  constructor(onStateChange: (state: AgentState) => void) {
    this.onStateChange = onStateChange;
  }

  private setState(update: Partial<AgentState>) {
    this.state = { ...this.state, ...update };
    if (update.thoughts) {
        // Append thoughts instead of overwrite if array passed?
        // For simplicity, let's assume the caller passes the full new array or we append here.
        // Actually, let's just make sure we don't lose old thoughts if we want to keep them.
        // But for now, simple assignment.
    }
    this.onStateChange(this.state);
  }

  private addThought(text: string) {
    this.setState({ thoughts: [...this.state.thoughts, text] });
  }

  async init(modelId?: string) {
    this.setState({ status: 'initializing' });

    // Load Schema
    const schemaRes = await fetch('/assets/schema.json');
    schemaStr = JSON.stringify(await schemaRes.json(), null, 2);

    // Init Workers
    const p1 = workerRequest(dbWorker, 'INIT_DB');

    // For LLM, we need to handle progress streaming separately
    const p2 = new Promise<void>((resolve, reject) => {
       const id = 'init-llm';
       llmWorker.postMessage({ type: 'INIT_LLM', payload: { modelId }, id });

       const handler = (e: MessageEvent) => {
         if (e.data.type === 'PROGRESS') {
           this.addThought(`Loading Model: ${e.data.payload.text}`);
         } else if (e.data.type === 'INIT_SUCCESS' && e.data.id === id) {
           llmWorker.removeEventListener('message', handler);
           resolve();
         } else if (e.data.type === 'ERROR' && e.data.id === id) {
           llmWorker.removeEventListener('message', handler);
           reject(new Error(e.data.error));
         }
       };
       llmWorker.addEventListener('message', handler);
    });

    // Init RAG
    const p3 = initRAG();

    await Promise.all([p1, p2, p3]);
    this.setState({ status: 'idle', thoughts: ['System Ready.'] });
  }

  async processQuery(userQuery: string, history: Message[]) {
    this.setState({ status: 'thinking', thoughts: [], error: undefined });

    try {
      // 1. RAG Retrieval
      this.addThought("Searching for relevant examples...");
      const examples = await retrieveExamples(userQuery);
      this.addThought(`Found examples:\n${examples}`);

      // 2. SQL Generation Loop (Reflexion)
      let retries = 0;
      let sql = "";
      let data: any[] = [];
      let lastError = "";
      const maxRetries = 3;

      while (retries < maxRetries) {
        this.setState({ status: 'querying' });
        this.addThought(`Generating SQL (Attempt ${retries + 1})...`);

        // Prompt Construction
        const prompt = PROMPTS.sqlGenerator(userQuery, schemaStr, sql, lastError, examples);

        // Call LLM
        sql = await workerRequest(llmWorker, 'GENERATE', {
            messages: [{ role: 'user', content: prompt }]
        });

        // Clean SQL (sometimes models add markdown)
        sql = sql.replace(/```sql/g, '').replace(/```/g, '').trim();
        this.addThought(`Generated SQL: ${sql}`);

        try {
          this.setState({ status: 'executing' });
          data = await workerRequest(dbWorker, 'EXEC_SQL', { sql });
          this.addThought(`Query Successful. Rows returned: ${data.length}`);

          // If we get here, success! Break loop.
          break;
        } catch (e: any) {
          lastError = e.message || String(e);
          this.addThought(`SQL Error: ${lastError}`);
          this.setState({ status: 'reflecting' });
          retries++;
        }
      }

      if (retries === maxRetries) {
        throw new Error(`Failed to generate valid SQL after ${maxRetries} attempts.`);
      }

      // 3. Final Answer
      this.setState({ status: 'answering' });
      const dataStr = JSON.stringify(data, null, 2);
      // Truncate if too long to avoid context window issues
      const truncatedData = dataStr.length > 2000 ? dataStr.substring(0, 2000) + "...(truncated)" : dataStr;

      const answerPrompt = PROMPTS.responder(JSON.stringify(history), truncatedData);
      const answer = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: answerPrompt }]
      });

      this.setState({ status: 'idle' });
      return { answer, data, sql };

    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      throw err;
    }
  }
}
