import { PROMPTS } from './prompts';
import { LangfuseWeb } from 'langfuse';

// Optional: Langfuse for local observability (configured via Suite)
const langfuse = new LangfuseWeb({
  publicKey: "pk-lf-...", // Placeholder, set via environment or config
  baseUrl: "http://localhost:3000",
});

// Types
type Message = { role: 'user' | 'assistant' | 'system', content: string };
type AgentState = {
  status: 'idle' | 'initializing' | 'thinking' | 'querying' | 'executing' | 'reflecting' | 'answering' | 'error';
  thoughts: string[];
  error?: string;
};

const VALID_OWNER_NAMES = [
  "Dylan", "Dan", "Zach", "Chris", "Sean", "Jack",
  "Lac", "Will", "Josh", "Jake", "Fitz", "Mark", "Nick"
];

// Worker Interfaces
const dbWorker = new Worker(new URL('../workers/db.worker.ts', import.meta.url), { type: 'module' });
const llmWorker = new Worker(new URL('../workers/llm.worker.ts', import.meta.url), { type: 'module' });
const ragWorker = new Worker(new URL('../workers/rag.worker.ts', import.meta.url), { type: 'module' });

// Helper to wrap Worker messaging in Promises
function workerRequest(worker: Worker, type: string, payload: any = {}, onChunk?: (chunk: string) => void): Promise<any> {
  return new Promise((resolve, reject) => {
    const id = Math.random().toString(36).substring(7);

    const handler = (e: MessageEvent) => {
      if (e.data.id === id) {
        if (e.data.type === 'CHUNK' && onChunk) {
          onChunk(e.data.payload);
        } else if (e.data.type === 'GENERATE_SUCCESS' || e.data.type === 'INIT_SUCCESS') {
          worker.removeEventListener('message', handler);
          resolve(e.data.payload);
        } else if (e.data.type === 'ERROR') {
          worker.removeEventListener('message', handler);
          reject(new Error(e.data.error));
        }
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
    this.onStateChange(this.state);
  }

  private addThought(text: string) {
    this.setState({ thoughts: [...this.state.thoughts, text] });
  }

  private addThoughtChunk(chunk: string) {
    const lastIdx = this.state.thoughts.length - 1;
    if (lastIdx >= 0) {
      const updated = [...this.state.thoughts];
      updated[lastIdx] += chunk;
      this.setState({ thoughts: updated });
    } else {
      this.addThought(chunk);
    }
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
      console.log("Initializing RAG worker...");
      const p3 = workerRequest(ragWorker, 'INIT_RAG');

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

    const trace = langfuse.trace({
      name: "query-pipeline",
      input: { userQuery, history },
    });

    try {
      // 0. Routing / Pre-processing
      if (!this.isAnalyticalQuery(userQuery)) {
        trace.update({ tags: ["conversational"] });
        this.addThought("Detected non-analytical query. Answering directly...");
        this.setState({ status: 'answering' });
        const answerPrompt = `
          The user said: "${userQuery}".
          Respond naturally as a Fantasy Football Assistant. 
          If they said hi, say hi back and offer help with stats or matchups.
          If they asked for help, explain that you can answer questions about league history, standings, and player stats.
        `;
        const answer = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: answerPrompt }]
        });

        trace.update({ output: answer });
        this.setState({ status: 'idle' });
        return { answer, data: [], sql: "" };
      }

      // 0.5 Query Enhancement (Context Resolution)
      let activeQuery = userQuery;
      if (history.length > 0) {
        const span = trace.span({ name: "query-enhancement" });
        this.addThought("Resolving context from conversation history: ");
        const historyStr = history.map(m => `${m.role}: ${m.content}`).join('\n');
        const enhancementPrompt = PROMPTS.queryEnhancer(historyStr, userQuery, VALID_OWNER_NAMES);
        activeQuery = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: enhancementPrompt }],
          stream: true
        }, (chunk) => this.addThoughtChunk(chunk));
        span.end({ output: activeQuery });
      }

      // 1. RAG Retrieval
      const ragSpan = trace.span({ name: "rag-retrieval" });
      this.addThought("Searching for relevant SQLite examples in my knowledge base...");
      const examples = await workerRequest(ragWorker, 'RETRIEVE', { query: activeQuery });
      if (examples) {
        this.addThought("Found similar questions to help guide SQL generation.");
      }
      ragSpan.end({ output: examples });

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
      const maxRetries = 2; // Defensive: don't loop forever

      while (retries < maxRetries) {
        const sqlSpan = trace.span({ name: `sql-generation-attempt-${retries}` });
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

        try {
          this.setState({ status: 'executing' });
          this.addThought("Executing query against the local database...");
          // Correct command is 'EXEC_SQL'
          data = await workerRequest(dbWorker, 'EXEC_SQL', { sql });

          if (data && !Array.isArray(data) && (data as any).error) {
            throw new Error((data as any).error);
          }

          this.addThought(`Query Successful. Retrieved ${data.length} rows.`);
          sqlSpan.end({ output: { sql, rowCount: data.length } });
          // If we get here, success! Break loop.
          break;
        } catch (e: any) {
          lastError = e.message || String(e);
          this.addThought(`SQL execution failed: ${lastError}`);
          this.setState({ status: 'reflecting' });
          sqlSpan.end({ error: lastError });
          retries++;
        }
      }

      // 3. Final Answer Generation (Streaming)
      this.setState({ status: 'answering' });
      const answerSpan = trace.span({ name: "final-answer" });

      // Defensive: If no data after retries, explain simply
      if (data.length === 0 && lastError) {
        this.addThought("Decision: Max retries reached with error. Formulating graceful fallback response: ");
      } else if (data.length === 0) {
        this.addThought("Decision: No data found for this specific query. Formulating natural response: ");
      } else {
        this.addThought("Analyzing results and formulating final response: ");
      }

      const historyStrAnswer = history.map(m => `${m.role}: ${m.content}`).join('\n');
      const dataStr = JSON.stringify(data);
      const truncatedData = dataStr.length > 3000 ? dataStr.substring(0, 3000) + "...(truncated)" : dataStr;

      const answerPrompt = PROMPTS.responder(historyStrAnswer, truncatedData);

      const answer = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: answerPrompt }],
        stream: true
      }, (chunk) => this.addThoughtChunk(chunk));

      answerSpan.end({ output: answer });
      trace.update({ output: answer });

      this.setState({ status: 'idle' });
      return { answer, data, sql };

    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      console.error("Agent processQuery error:", err);
      // We don't return to idle immediately here to let the UI show the error status,
      // but handleSubmit in App.tsx should handle the message.
      // Actually, to prevent the "hang", we SHOULD return to idle after a brief moment
      // or ensure the UI can still submit.
      // Best approach: allow 'error' as a state that unlocks the input.
      throw err;
    } finally {
      // If we didn't hit an explicit error state that we want to persist, 
      // or if we just want to unlock the UI:
      if (this.state.status !== 'error') {
        this.setState({ status: 'idle' });
      } else {
        // Even in error, we want to allow the user to try again
        // After 3 seconds, return to idle
        setTimeout(() => {
          if (this.state.status === 'error') {
            this.setState({ status: 'idle' });
          }
        }, 3000);
      }
    }
  }
}
