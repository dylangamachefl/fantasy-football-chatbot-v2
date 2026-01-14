import { PROMPTS } from './prompts';
import { LangfuseWeb } from 'langfuse';
import type { Message, AgentState, WorkingMemory } from '../types';

const langfuse = new LangfuseWeb({
  publicKey: "pk-lf-05fea78a-def0-4143-847d-f9b06912f701",
  baseUrl: "https://cloud.langfuse.com",
});

export const VALID_OWNER_NAMES = [
  "Dylan", "Dan", "Zach", "Chris", "Sean", "Jack",
  "Lac", "Will", "Josh", "Jake", "Fitz", "Mark", "Nick"
];

// Worker Interfaces
const dbWorker = new Worker(new URL('../workers/db.worker.ts', import.meta.url), { type: 'module' });
const llmWorker = new Worker(new URL('../workers/llm.worker.ts', import.meta.url), { type: 'module' });
const ragWorker = new Worker(new URL('../workers/rag.worker.ts', import.meta.url), { type: 'module' });

// Helper to wrap Worker messaging in Promises
function workerRequest(
  worker: Worker,
  type: string,
  payload: any = {},
  onChunk?: (chunk: string) => void,
  parentSpan?: any
): Promise<any> {
  const span = parentSpan?.span({
    name: `worker-request:${type}`,
    input: payload,
  });

  return new Promise((resolve, reject) => {
    const id = Math.random().toString(36).substring(7);

    const handler = (e: MessageEvent) => {
      if (e.data.id === id) {
        if (e.data.type === 'CHUNK' && onChunk) {
          onChunk(e.data.payload);
        } else if ([
          'GENERATE_SUCCESS',
          'INIT_SUCCESS',
          'RETRIEVE_SUCCESS',
          'RETRIEVE_BATCH_SUCCESS',
          'EXEC_SQL_SUCCESS',
          'VALIDATE_SQL_SUCCESS'
        ].includes(e.data.type)) {
          worker.removeEventListener('message', handler);

          // Capture metadata if present
          const output = e.data.payload;
          const metadata = e.data.metadata || {};

          span?.end({
            output: output,
            metadata: {
              ...metadata,
              ...(typeof output === 'object' ? output : {})
            }
          });

          resolve(e.data.payload);
        } else if (e.data.type === 'ERROR') {
          worker.removeEventListener('message', handler);
          span?.end({ output: e.data.error, level: 'ERROR' });
          reject(new Error(e.data.error));
        }
      }
    };

    worker.addEventListener('message', handler);

    // Propagate trace context
    const traceContext = parentSpan ? {
      traceId: parentSpan.traceId,
      parentSpanId: parentSpan.id
    } : undefined;

    worker.postMessage({ type, payload, id, traceContext });
  });
}

// Global Schema Cache
let schemaData: any = null;

export class Agent {
  private onStateChange: (state: AgentState) => void;
  private state: AgentState = { status: 'idle', thoughts: [] };
  private workingMemory: WorkingMemory = {
    Manager: "None",
    Season: "None",
    Player: "None",
    Week: "None"
  };

  private lastTraceId: string | null = null;
  private identity: string | null = localStorage.getItem('ff_manager_identity');
  private managerBio: string | null = null;

  constructor(onStateChange: (state: AgentState) => void) {
    this.onStateChange = onStateChange;
    if (this.identity) {
      this.workingMemory.Manager = this.identity;
    }
  }

  private setState(update: Partial<AgentState>) {
    this.state = { ...this.state, ...update, identity: this.identity || undefined, managerBio: this.managerBio || undefined };
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
      if (!schemaRes.ok) throw new Error(`Failed to fetch schema.json`);
      schemaData = await schemaRes.json();

      // Init Workers
      const p1 = workerRequest(dbWorker, 'INIT_DB');
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
      const p3 = workerRequest(ragWorker, 'INIT_RAG');

      await Promise.all([p1, p2, p3]);

      // Bio Fetch
      if (this.identity) {
        await this.fetchManagerBio();
      }

      this.setState({ status: 'idle', thoughts: ['System Ready. Transmission Secured.'] });
    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      throw err;
    }
  }

  private async fetchManagerBio() {
    try {
      this.addThought(`Retrieving dossier for ${this.identity}...`);
      const sql = `SELECT * FROM Fact_Manager_Career_Leaderboard WHERE owner_name = '${this.identity}'`;
      const response = await workerRequest(dbWorker, 'EXEC_SQL', { sql });
      const data = Array.isArray(response) ? response : response.rows;

      if (data && data.length > 0) {
        const bio = data[0];
        this.managerBio = `Manager ${bio.owner_name} has ${bio.career_wins} career wins (${(bio.career_win_percentage * 100).toFixed(1)}% win rate) and ${bio.championships_won} championships. Average finish: ${bio.avg_final_standing}.`;
        console.log("[Agent] Manager Bio Loaded:", this.managerBio);
      }
    } catch (e) {
      console.warn("[Agent] Failed to fetch manager bio:", e);
    }
  }

  private isAnalyticalQuery(query: string): boolean {
    const lower = query.toLowerCase().trim();
    const analyticalKeywords = [
      'who', 'what', 'when', 'where', 'how', 'stats', 'score',
      'points', 'win', 'loss', 'standing', 'rank', 'draft', 'matchup',
      'champion', 'best', 'worst', 'most', 'least', 'joke', 'lore', 'party'
    ];
    return analyticalKeywords.some(kw => lower.includes(kw)) || query.length > 15;
  }

  async processQuery(userQuery: string, history: Message[]) {
    this.setState({ status: 'thinking', thoughts: [], error: undefined });
    const memoryStr = JSON.stringify(this.workingMemory);

    // Optional Langfuse tracing
    let trace: any = null;
    try {
      if (typeof (langfuse as any).trace === 'function') {
        trace = (langfuse as any).trace({
          name: 'agent-process-query',
          input: { userQuery, history, workingMemory: this.workingMemory },
        });
        this.lastTraceId = trace?.id || null;
      }
    } catch (e) {
      console.warn('[Agent] Langfuse tracing unavailable:', e);
    }

    try {
      // 0. Conversational Check
      if (!this.isAnalyticalQuery(userQuery)) {
        this.addThought("Detected non-analytical query. Answering directly...");
        this.setState({ status: 'answering' });
        const answerPrompt = `User: "${userQuery}". Respond as a helpful Fantasy Assistant.`;
        const answerSpan = trace?.span?.({ name: 'conversational-answer', input: answerPrompt });
        const answer = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: answerPrompt }]
        }, undefined, answerSpan);
        answerSpan?.end?.({ output: answer });

        this.setState({ status: 'idle' });
        trace?.end?.({ output: answer, metadata: { thoughts: this.state.thoughts } });
        return { answer, data: [], sql: "" };
      }

      // 0.5 Phase 7: Slot Filling & Working Memory Update
      const slotSpan = trace?.span?.({ name: 'slot-filling', input: { userQuery, memory: this.workingMemory } });
      this.addThought("Updating working memory... ");
      const slotFillerOutput = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: PROMPTS.slotFiller(userQuery, memoryStr) }],
        jsonMode: true
      }, undefined, slotSpan);
      try {
        const parsedMemory = typeof slotFillerOutput === 'string' ? JSON.parse(slotFillerOutput) : slotFillerOutput;
        this.workingMemory = { ...this.workingMemory, ...parsedMemory };
        console.log("[Agent] Working Memory Updated:", this.workingMemory);
        slotSpan?.end?.({ output: parsedMemory });
      } catch (e) {
        console.warn("[Agent] Slot filler failed to parse, using existing memory");
        slotSpan?.end?.({ output: "Failed to parse", level: "WARNING" });
      }

      // 0.6 Phase 6: Query Enhancement with Memory
      let activeQuery = userQuery;
      this.addThought("Resolving context... ");
      const historyStr = history.slice(-5).map(m => `${m.role}: ${m.content}${m.sql ? ` (Used SQL: ${m.sql})` : ''}`).join('\n');
      const enhancedQueryPrompt = `
        ${PROMPTS.queryEnhancer(historyStr, userQuery, VALID_OWNER_NAMES, this.identity || "Unknown Manager")}
        CURRENT ENTITIES IN MEMORY: ${memoryStr}
        Ensure the rewritten query includes these entities if they are relevant to the user's pronouns or follow-up.
      `;

      const enhancementSpan = trace?.span?.({ name: 'query-enhancement', input: enhancedQueryPrompt });
      activeQuery = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: enhancedQueryPrompt }],
        stream: true
      }, (chunk) => this.addThoughtChunk(chunk), enhancementSpan);
      enhancementSpan?.end?.({ output: activeQuery });

      // 1. Parallel RAG Retrieval (SQL & LORE)
      this.addThought("Retrieving knowledge... ");
      const ragSpan = trace?.span?.({ name: 'rag-retrieval', input: { query: activeQuery } });
      const ragResults = await workerRequest(ragWorker, 'RETRIEVE_BATCH', [
        { query: activeQuery, collection: 'SQL', k: 3 },
        { query: activeQuery, collection: 'LORE', k: 3 }
      ], undefined, ragSpan);
      const [sqlExamples, loreFacts] = ragResults;
      ragSpan?.end?.({ output: { sqlExamplesCount: sqlExamples.length, loreFactsCount: loreFacts.length } });

      const relevantLore = loreFacts.filter((f: any) => f.score > 0.6);
      let loreContext = relevantLore.map((f: any) => `${f.topic}: ${f.context}`).join('\n');
      if (this.managerBio) {
        loreContext = `CONTEXT ON USER (${this.identity}): ${this.managerBio}\n\n${loreContext}`;
      }
      if (relevantLore.length > 0) this.addThought(`Found ${relevantLore.length} lore facts.`);

      // 2. Table Routing & Dynamic Schema Pruning
      this.addThought("Selecting tables... ");
      const tables = schemaData?.tables || [];
      const tableDescriptions = tables.map((t: any) => `Table: ${t.table_name}, Description: ${t.description}`).join('\n');

      const routingSpan = trace?.span?.({ name: 'table-routing', input: { activeQuery, tableDescriptions } });
      const routerOutput = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: PROMPTS.tableRouter(activeQuery, tableDescriptions) }],
        jsonMode: true
      }, undefined, routingSpan);

      let selectedTables: string[] = [];
      let isSqlQuery = true;
      try {
        const parsed = typeof routerOutput === 'string' ? JSON.parse(routerOutput) : routerOutput;
        selectedTables = parsed.selected_tables || [];
        isSqlQuery = parsed.is_sql_query !== false;

        const exampleTables = sqlExamples.flatMap((ex: any) => ex.tables_used || []);
        selectedTables = Array.from(new Set([...selectedTables, ...exampleTables]));
        this.addThought(`Using Tables: ${selectedTables.join(', ')}`);
        routingSpan?.end?.({ output: { selectedTables, isSqlQuery } });
      } catch (e) {
        selectedTables = tables.map((t: any) => t.table_name);
        routingSpan?.end?.({ output: "Routing parse error", level: "WARNING" });
      }

      const filteredSchemaParts = ["DATABASE SCHEMA:\n"];
      for (const t of tables) {
        if (selectedTables.includes(t.table_name)) {
          filteredSchemaParts.push(`Table: ${t.table_name}\nColumns: ${JSON.stringify(t.columns)}\n`);
        }
      }
      const filteredSchemaStr = filteredSchemaParts.join('\n');

      // 3. SQL Generation & Validation Loop (Reflexion)
      let sql = "";
      let data: any[] = [];
      if (isSqlQuery && selectedTables.length > 0) {
        let retries = 0;
        let lastError = "";
        const examplesStr = sqlExamples.map((s: any, i: number) => `Ex ${i + 1}: Q: ${s.question}\nSQL: ${s.sql}`).join('\n\n');

        const sqlLoopSpan = trace?.span?.({ name: 'sql-generation-loop', input: { activeQuery, retriesLimit: 2 } });
        while (retries < 2) {
          this.setState({ status: 'querying' });
          this.addThought(retries > 0 ? "Retrying SQL generation..." : "Generating SQL...");

          const genSpan = sqlLoopSpan?.span?.({ name: `sql-gen-attempt-${retries}`, input: { lastError } });
          sql = await workerRequest(llmWorker, 'GENERATE', {
            messages: [{ role: 'user', content: PROMPTS.sqlGenerator(activeQuery, filteredSchemaStr, sql, lastError, examplesStr) }]
          }, undefined, genSpan);
          sql = sql.replace(/```sql/g, '').replace(/```/g, '').trim();

          const validation = await workerRequest(dbWorker, 'VALIDATE_SQL', { sql }, undefined, genSpan);
          if (validation.valid) {
            try {
              this.setState({ status: 'executing' });
              const response = await workerRequest(dbWorker, 'EXEC_SQL', { sql }, undefined, genSpan);
              data = Array.isArray(response) ? response : response.rows;

              if (response.warning) {
                this.addThought(`Caution: ${response.warning}`);
              }

              genSpan?.end?.({ output: { sql, dataCount: data.length } });

              // Auto-score for success
              if (data.length > 0) {
                trace?.score?.({
                  name: "sql-success",
                  value: 1,
                  comment: "SQL produced data"
                });
              }
              break;
            } catch (e: any) {
              lastError = e.message;
              genSpan?.end?.({ output: lastError, level: 'ERROR' });
              trace?.update?.({ tags: ["sql-retry"] });
              retries++;
            }
          } else {
            lastError = validation.error;
            this.addThought(`Validation failed: ${lastError}`);
            genSpan?.end?.({ output: lastError, level: 'ERROR' });
            trace?.update?.({ tags: ["sql-retry"] });
            retries++;
          }
        }
        sqlLoopSpan?.end?.({ output: { finalSql: sql, finalDataCount: data.length, attempts: retries + 1 } });
      }

      // 4. Final Responder
      this.setState({ status: 'answering' });
      this.addThought("Answering... ");
      const dataStr = JSON.stringify(data.slice(0, 50)).substring(0, 3000);

      const responderSpan = trace?.span?.({ name: 'final-responder', input: { dataCount: data.length, loreContext } });
      const answer = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: PROMPTS.responder(historyStr, dataStr, loreContext) }],
        stream: true
      }, (chunk) => this.addThoughtChunk(chunk), responderSpan);
      responderSpan?.end?.({ output: answer });

      this.setState({ status: 'idle' });
      trace?.end?.({ output: answer, metadata: { thoughts: this.state.thoughts, memory: this.workingMemory } });
      return { answer, data, sql };

    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      trace?.end?.({ output: err.message, level: 'ERROR', metadata: { thoughts: this.state.thoughts } });
      setTimeout(() => this.setState({ status: 'idle' }), 5000);
      throw err;
    }
  }

  async scoreLastTrace(value: number, comment?: string) {
    if (!this.lastTraceId) return;

    langfuse.score({
      traceId: this.lastTraceId,
      name: "user-feedback",
      value: value,
      comment: comment
    });
  }
}
