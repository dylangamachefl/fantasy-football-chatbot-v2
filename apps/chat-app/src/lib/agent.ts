import { PROMPTS } from './prompts';
import Logger from './logger';
import type { Message, AgentState, WorkingMemory } from '../types';

export const VALID_OWNER_NAMES = [
  "Dylan", "Dan", "Zach", "Chris", "Sean", "Jack",
  "Lac", "Will", "Josh", "Jake", "Fitz", "Mark", "Nick"
];

const DB_ENTITY_MAP = `
- MANAGERS: Tracked for Championships, Career Wins, Final Standings, Draft Value.
- PLAYERS: Tracked for Points, Passing/Rushing/Receiving Stats, Weekly Performance.
- MATCHUPS: Tracked for head-to-head scores and margins.
`;

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
    Week: "None",
    EntityType: "None"
  };


  private identity: string | null = localStorage.getItem('ff_manager_identity');
  private isProcessing: boolean = false;
  private lastQueryId: string | null = null;  // For linking feedback to queries

  constructor(onStateChange: (state: AgentState) => void) {
    this.onStateChange = onStateChange;
    if (this.identity) {
      this.workingMemory.Manager = this.identity;
    }
  }

  private setState(update: Partial<AgentState>) {
    this.state = { ...this.state, ...update, identity: this.identity || undefined };
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

      // Bio Fetch removed - focusing on database-driven facts only

      this.setState({ status: 'idle', thoughts: ['System Ready. Transmission Secured.'] });
    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      throw err;
    }
  }



  private isAnalyticalQuery(query: string): boolean {
    const lower = query.toLowerCase().trim();
    const analyticalKeywords = [
      'who', 'what', 'when', 'where', 'how', 'stats', 'score',
      'points', 'win', 'loss', 'standing', 'rank', 'draft', 'matchup',
      'champion', 'best', 'worst', 'most', 'least', 'joke', 'lore', 'party'
    ];
    return analyticalKeywords.some(kw => lower.includes(kw)) || query.length > 25;
  }

  async processQuery(userQuery: string, history: Message[]) {
    // Concurrency guard: prevent double-execution
    if (this.isProcessing) {
      console.warn('[Agent] Query already in progress, ignoring duplicate call');
      return;
    }

    this.isProcessing = true;

    try {
      const startTime = Date.now();  // Track query duration
      this.setState({ status: 'thinking', thoughts: [], error: undefined });
      const memoryStr = JSON.stringify(this.workingMemory);

      // Langfuse tracing disabled: LangfuseWeb doesn't support server-side trace() API
      // To enable tracing, you need to proxy traces through a backend server
      const trace: any = null;

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

          // Preserve identity: Don't let the slot filler reset Manager to "None" if we have an identity
          if (this.identity && parsedMemory.Manager === "None") {
            parsedMemory.Manager = this.identity;
          }

          this.workingMemory = { ...this.workingMemory, ...parsedMemory };
          console.log("[Agent] Working Memory Updated:", this.workingMemory);
          slotSpan?.end?.({ output: parsedMemory });
        } catch (e) {
          console.warn("[Agent] Slot filler failed to parse, using existing memory");
          slotSpan?.end?.({ output: "Failed to parse", level: "WARNING" });
        }

        // 0.55 Determine if this is a personal query (Context Gating)
        const isPersonalQuery = this.workingMemory.Manager === this.identity
          || userQuery.toLowerCase().match(/\b(me|my|i|myself)\b/) !== null;
        console.log("[Agent] Personal Query:", isPersonalQuery);

        // 0.6 Pre-Retrieval for Schema Clues (Phase 3)
        this.addThought("Searching for schema clues... ");
        const preRetrieval = await workerRequest(ragWorker, 'RETRIEVE', {
          query: userQuery,
          collection: 'SQL',
          k: 1
        });
        const schemaHint = preRetrieval.length > 0 ? `Relevant Table Hint: ${preRetrieval[0].table_name}` : "";

        // 0.7 Query Enhancement with Memory & Schema Hints
        let activeQuery = userQuery;
        this.addThought("Resolving context... ");
        const historyStr = history.slice(-5).map(m => `${m.role}: ${m.content}${m.sql ? ` (Used SQL: ${m.sql})` : ''}`).join('\n');

        // Use working memory for manager name (falls back to identity if not set)
        const managerName = this.workingMemory.Manager !== "None" ? this.workingMemory.Manager : (this.identity || "Unknown Manager");

        const enhancedQueryPrompt = `
          ${PROMPTS.queryEnhancer(historyStr, userQuery, VALID_OWNER_NAMES, managerName, DB_ENTITY_MAP)}
          
          ${schemaHint ? `SCHEMA HINT: ${schemaHint}` : ""}
          CURRENT ENTITIES IN MEMORY: ${JSON.stringify(this.workingMemory)}
          Ensure the rewritten query includes these entities if they are relevant to the user's pronouns or follow-up.
        `;

        const enhancementSpan = trace?.span?.({ name: 'query-enhancement', input: enhancedQueryPrompt });
        activeQuery = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: enhancedQueryPrompt }],
          stream: true
        }, (chunk) => this.addThoughtChunk(chunk), enhancementSpan);
        enhancementSpan?.end?.({ output: activeQuery });

        // 1. RAG Retrieval (SQL only - lore removed for data supremacy)
        this.addThought("Retrieving knowledge... ");
        const ragSpan = trace?.span?.({ name: 'rag-retrieval', input: { query: activeQuery } });
        const ragResults = await workerRequest(ragWorker, 'RETRIEVE_BATCH', [
          { query: activeQuery, collection: 'SQL', k: 3 }
        ], undefined, ragSpan);
        const [sqlExamples] = ragResults;
        ragSpan?.end?.({ output: { sqlExamplesCount: sqlExamples.length } });

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

            // Pass manager name and working memory to SQL generator for context
            const sqlPrompt = PROMPTS.sqlGenerator(activeQuery, filteredSchemaStr, managerName, this.workingMemory, sql, lastError, examplesStr);

            const sqlOutput = await workerRequest(llmWorker, 'GENERATE', {
              messages: [{ role: 'user', content: sqlPrompt }],
              jsonMode: true
            }, undefined, genSpan);

            try {
              const parsed = typeof sqlOutput === 'string' ? JSON.parse(sqlOutput) : sqlOutput;
              sql = parsed.sql || "";
              const reasoning = parsed.reasoning || "";

              if (reasoning) {
                this.addThought(`Plan: ${reasoning}`);
              }
            } catch (e) {
              console.warn("[Agent] SQL generator failed to parse JSON, falling back to raw string");
              sql = typeof sqlOutput === 'string' ? sqlOutput : JSON.stringify(sqlOutput);
            }

            sql = sql.replace(/```sql/g, '').replace(/```/g, '').trim();

            // Safety: Replace common placeholders with actual manager name
            if (managerName && managerName !== "None" && managerName !== "Unknown Manager") {
              sql = sql.replace(/'Your Manager Name'/gi, `'${managerName}'`);
              sql = sql.replace(/"Your Manager Name"/gi, `"${managerName}"`);
              sql = sql.replace(/\[Manager Name\]/gi, managerName);
              sql = sql.replace(/'\{manager_name\}'/gi, `'${managerName}'`);
            }

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

        const responderSpan = trace?.span?.({ name: 'final-responder', input: { dataCount: data.length } });
        const answer = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: PROMPTS.responder(historyStr, dataStr) }],
          stream: true
        }, (chunk) => this.addThoughtChunk(chunk), responderSpan);
        responderSpan?.end?.({ output: answer });

        this.setState({ status: 'idle' });
        trace?.end?.({ output: answer, metadata: { thoughts: this.state.thoughts, memory: this.workingMemory } });

        // Log query for analysis and teacher-student flywheel
        this.lastQueryId = Logger.logQuery({
          userQuery,
          workingMemory: this.workingMemory,
          sqlGenerated: sql,
          dataRows: data.length,
          answer,
          durationMs: Date.now() - startTime,
          thoughtProcess: [...this.state.thoughts],  // Copy thoughts
          tablesUsed: selectedTables
        });

        return { answer, data, sql };

      } catch (err: any) {
        this.setState({ status: 'error', error: err.message });
        trace?.end?.({ output: err.message, level: 'ERROR', metadata: { thoughts: this.state.thoughts } });
        setTimeout(() => this.setState({ status: 'idle' }), 5000);
        throw err;
      }
    } finally {
      this.isProcessing = false;
    }
  }

  async scoreLastTrace(value: number, comment?: string) {
    if (!this.lastQueryId) {
      console.warn('[Agent] No query ID to link feedback to');
      return;
    }

    Logger.logFeedback(this.lastQueryId, value, comment);
    console.log('[Agent] Feedback logged:', { queryId: this.lastQueryId, value, comment });
  }
}
