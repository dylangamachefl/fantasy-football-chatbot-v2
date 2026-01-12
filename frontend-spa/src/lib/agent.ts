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

    try {
      // Load Schema
      console.log("Loading schema...");
      const schemaRes = await fetch('/assets/schema.json');
      if (!schemaRes.ok) {
        throw new Error(`Failed to fetch schema.json: ${schemaRes.status} ${schemaRes.statusText}`);
      }
      const schemaData = await schemaRes.json();
      schemaStr = JSON.stringify(schemaData, null, 2);
      console.log("Schema loaded successfully.");

      // Init Workers
      console.log("Initializing database worker...");
      const p1 = workerRequest(dbWorker, 'INIT_DB');

      // For LLM, we need to handle progress streaming separately
      console.log("Initializing LLM worker with model:", modelId);
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
    } catch (err: any) {
      console.error("Initialization failed:", err);
      this.setState({ status: 'error', error: err.message });
      throw err;
    }
  }

  private isAnalyticalQuery(query: string): boolean {
    const lower = query.toLowerCase().trim();
    // Simple greetings or very short queries
    const greetings = ['hi', 'hello', 'hey', 'yo', 'sup', 'help'];
    if (greetings.includes(lower)) return false;

    // Check for "question words" or analytical keywords
    const analyticalKeywords = [
      'who', 'what', 'when', 'where', 'how many', 'stats', 'score',
      'points', 'win', 'loss', 'standing', 'rank', 'draft', 'matchup',
      'champion', 'leaderboard', 'best', 'worst', 'most', 'least'
    ];
    return analyticalKeywords.some(kw => lower.includes(kw));
  }

  async processQuery(userQuery: string, history: Message[]) {
    this.setState({ status: 'thinking', thoughts: [], error: undefined });

    try {
      // 0. Routing / Pre-processing
      if (!this.isAnalyticalQuery(userQuery)) {
        // ... (existing greeting logic)
      }

      // 0.5 Query Enhancement (Context Resolution)
      let activeQuery = userQuery;
      if (history.length > 0) {
        this.addThought("Resolving context from conversation history...");
        const historyStr = history.map(m => `${m.role}: ${m.content}`).join('\n');
        const enhancementPrompt = PROMPTS.queryEnhancer(historyStr, userQuery);
        activeQuery = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: enhancementPrompt }]
        });
        this.addThought(`Enhanced Query: ${activeQuery}`);
      }

      // 1. RAG Retrieval
      this.addThought("Searching for relevant SQLite examples in my knowledge base...");
      const examples = await retrieveExamples(activeQuery);
      if (examples) {
        this.addThought("Found similar questions to help guide SQL generation.");
      }

      // 1.5 Table Routing & Schema Filtering
      this.addThought("Identifying relevant database tables for this query...");
      // Get table descriptions from our loaded schema data
      const schemaData = JSON.parse(schemaStr);
      const tableDescriptions = schemaData.map((t: any) => `${t.table_name}: ${t.description}`).join('\n');

      const routerOutput = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: PROMPTS.tableRouter(activeQuery, tableDescriptions) }],
        jsonMode: true
      });

      let selectedTables: string[] = [];
      try {
        const parsed = typeof routerOutput === 'string' ? JSON.parse(routerOutput) : routerOutput;
        selectedTables = parsed.selected_tables || [];
        this.addThought(`Selected Tables: ${selectedTables.join(', ')}`);
        this.addThought(`Reasoning: ${parsed.reasoning}`);
      } catch (e) {
        console.warn("Failed to parse router output, falling back to full schema", e);
      }

      // Core tables that should always be included
      const CORE_TABLES = ["FantasyOwners_LLM", "FantasySeasons_LLM", "FantasyTeams_LLM", "FantasyMatchups_LLM"];
      const finalTablesSet = new Set([...CORE_TABLES, ...selectedTables]);

      // Filter schema
      const filteredSchemaData = schemaData.filter((t: any) => finalTablesSet.has(t.table_name));
      const filteredSchemaStr = JSON.stringify(filteredSchemaData, null, 2);

      // 2. SQL Generation Loop (Reflexion)
      let retries = 0;
      let sql = "";
      let data: any[] = [];
      let lastError = "";
      const maxRetries = 3;

      while (retries < maxRetries) {
        this.setState({ status: 'querying' });
        const attemptMsg = retries > 0 ? ` (Attempt ${retries + 1} - Fixing previous error)` : "";
        this.addThought(`Generating SQL query based on filtered schema${attemptMsg}...`);

        // Prompt Construction
        const prompt = PROMPTS.sqlGenerator(activeQuery, filteredSchemaStr, sql, lastError, examples);

        // Call LLM
        sql = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: prompt }]
        });

        // Clean SQL (sometimes models add markdown)
        sql = sql.replace(/```sql/g, '').replace(/```/g, '').trim();
        this.addThought(`Generated SQL: ${sql}`);

        try {
          this.setState({ status: 'executing' });
          this.addThought("Executing query against the local database...");
          data = await workerRequest(dbWorker, 'EXEC_SQL', { sql });
          this.addThought(`Query Successful. Retrieved ${data.length} rows.`);

          // If we get here, success! Break loop.
          break;
        } catch (e: any) {
          lastError = e.message || String(e);
          this.addThought(`SQL execution failed: ${lastError}`);
          this.setState({ status: 'reflecting' });
          retries++;
        }
      }

      if (retries === maxRetries) {
        throw new Error(`Failed to generate valid SQL after ${maxRetries} attempts.`);
      }

      // 3. Final Answer
      this.addThought("Analyzing results and formulating final answer...");
      this.setState({ status: 'answering' });
      const dataStr = JSON.stringify(data, null, 2);
      // Truncate if too long to avoid context window issues
      const truncatedData = dataStr.length > 2000 ? dataStr.substring(0, 2000) + "...(truncated)" : dataStr;

      const answerPrompt = PROMPTS.responder(JSON.stringify(history), truncatedData);
      const answer = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: answerPrompt }]
      });

      this.setState({ status: 'idle', thoughts: [...this.state.thoughts, "Task complete."] });
      return { answer, data, sql };

    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      throw err;
    }
  }
}
