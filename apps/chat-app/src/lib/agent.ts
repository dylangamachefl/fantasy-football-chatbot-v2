import { PROMPTS } from './prompts';
import Logger from './logger';
import { DSPyInterpreter } from './dspy-interpreter';
import { generateSchemaMarkdown } from './utils';
import type { Message, AgentState, WorkingMemory } from '../types';

export const VALID_OWNER_NAMES = [
  "Dylan", "Dan", "Zach", "Chris", "Sean", "Jack",
  "Lac", "Will", "Josh", "Jake", "Fitz", "Mark", "Nick"
];

// Worker Interfaces
const dbWorker = new Worker(new URL('../workers/db.worker.ts', import.meta.url), { type: 'module' });
const llmWorker = new Worker(new URL('../workers/llm.worker.ts', import.meta.url), { type: 'module' });
const ragWorker = new Worker(new URL('../workers/rag.worker.ts', import.meta.url), { type: 'module' });

// Helper to safely parse JSON with fallback extraction
function safeParseJSON(text: string, expectedFields: string[]): any {
  try {
    return typeof text === 'string' ? JSON.parse(text) : text;
  } catch (e) {
    // Regex extraction fallback for malformed JSON
    console.warn('[Agent] JSON parse failed, attempting regex extraction:', e);
    const extracted: any = {};

    for (const field of expectedFields) {
      // Try to extract field value using various patterns
      const patterns = [
        new RegExp(`"${field}"\s*:\s*"([^"]*)"`),  // "field": "value"
        new RegExp(`"${field}"\s*:\s*\[([^\]]*)\]`),  // "field": [array]
        new RegExp(`${field}:\s*"([^"]*)"`),  // field: "value" (no quotes on key)
      ];

      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
          extracted[field] = match[1];
          break;
        }
      }
    }

    if (Object.keys(extracted).length > 0) {
      console.log('[Agent] Regex extraction recovered fields:', Object.keys(extracted));
      return extracted;
    }

    throw new Error(`Failed to parse JSON and regex extraction found no fields: ${text.substring(0, 100)}...`);
  }
}

// Helper to truncate observation strings to prevent prompt overflow
const MAX_OBSERVATION_LENGTH = 4000; // ~1000 tokens
function truncateObservations(obs: string): string {
  if (obs.length <= MAX_OBSERVATION_LENGTH) return obs;

  // Keep the last N observations (most recent)
  const lines = obs.split('\n');
  const recentLines = lines.slice(-20); // Keep last 20 lines
  const truncated = recentLines.join('\n');

  return `... [earlier observations truncated] ...\n${truncated}`;
}

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

    // Cleanup function to remove event listener
    const cleanup = () => worker.removeEventListener('message', handler);

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
          cleanup();

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
          cleanup();
          span?.end({ output: e.data.error, level: 'ERROR' });
          reject(new Error(e.data.error));
        } else {
          // Cleanup on any other unhandled message type to prevent leaks
          cleanup();
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
let compiledPrograms: Record<string, any> = {};

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

      // Dynamic Artifact Fetching (Flywheel Phase 5.1)
      try {
        const res = await fetch('/assets/artifacts/compiled_fantasy_agent.json');
        if (res.ok) {
          compiledPrograms = await res.json();
          console.log("[Agent] Loaded unified compiled agent artifacts:", Object.keys(compiledPrograms));
        } else {
          // Fallback check for legacy artifact
          const legacyRes = await fetch('/assets/artifacts/compiled_sql_generator.json');
          if (legacyRes.ok) {
            compiledPrograms['sql_generator'] = await legacyRes.json();
            console.log("[Agent] Loaded legacy compiled SQL generator artifact");
          }
        }
      } catch (e) {
        console.warn("[Agent] Compiled artifacts not found, using base prompts");
      }

      this.setState({ status: 'idle', thoughts: ['System Ready. Transmission Secured.'] });
    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      throw err;
    }
  }




  async processQuery(userQuery: string, history: Message[]) {
    // Concurrency guard: prevent double-execution
    if (this.isProcessing) {
      console.warn('[Agent] Query already in progress, ignoring duplicate call');
      return;
    }

    this.isProcessing = true;

    try {
      const startTime = Date.now();
      this.setState({ status: 'thinking', thoughts: [], error: undefined });
      const memoryStr = JSON.stringify(this.workingMemory);

      // 0. Intent Routing (Adaptive Orchestrator)
      this.addThought("Classifying intent...");
      let intentPrompt = "";
      if (compiledPrograms['intent_router']) {
        intentPrompt = DSPyInterpreter.render(compiledPrograms['intent_router'], { question: userQuery });
      } else {
        intentPrompt = PROMPTS.intentRouter(userQuery);
      }

      const routerOutput = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: intentPrompt }],
        jsonMode: true
      });

      const parsed = safeParseJSON(routerOutput, ['intent']);
      const intent = parsed.intent;

      if (intent === 'conversational') {
        this.addThought("Detected conversational query. Answering directly...");
        this.setState({ status: 'answering' });
        const answerPrompt = `User: "${userQuery}". Respond as a helpful Fantasy Assistant.`;
        const answer = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: answerPrompt }]
        });

        this.setState({ status: 'idle' });
        return { answer, data: [], sql: "" };
      }

      if (intent === 'league_history') {
        this.addThought("Detected league history query. Accessing archives...");
        this.setState({ status: 'thinking' });

        // Fetch league history context
        const historyRes = await fetch('/assets/league_history.json');
        const historyData = await historyRes.json();
        const historyContext = JSON.stringify(historyData);

        const historyPrompt = `
          Context: ${historyContext}
          User asked about league history: "${userQuery}". 
          Respond as a league historian using a witty, narrative tone based strictly on the provided context.
        `;

        const answer = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: historyPrompt }]
        });
        this.setState({ status: 'idle' });
        return { answer, data: [], sql: "" };
      }

      if (intent === 'league_rules') {
        this.addThought("Detected league rules query. Checking settings...");
        this.setState({ status: 'thinking' });

        // Fetch league rules context
        const rulesRes = await fetch('/assets/league_rules.json');
        const rulesData = await rulesRes.json();
        const rulesContext = JSON.stringify(rulesData);

        const rulesPrompt = `
          Context: ${rulesContext}
          User asked about league rules: "${userQuery}". 
          Respond as a rulebook authority based strictly on the provided context.
        `;

        const answer = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: rulesPrompt }]
        });
        this.setState({ status: 'idle' });
        return { answer, data: [], sql: "" };
      }

      // 1. Speculative Parallelism: Slot Filling & SQL RAG simultaneously
      this.addThought("Speculating entities and schema clues...");
      const [memoryUpdate, sqlHintsResult] = await Promise.all([
        workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: PROMPTS.slotFiller(userQuery, memoryStr) }],
          jsonMode: true
        }),
        workerRequest(ragWorker, 'RETRIEVE', {
          query: userQuery, collection: 'SQL', k: 3
        })
      ]);

      // Update state immediately to reflect new memory
      try {
        const parsedMemory = typeof memoryUpdate === 'string' ? JSON.parse(memoryUpdate) : memoryUpdate;
        if (this.identity && parsedMemory.Manager === "None") {
          parsedMemory.Manager = this.identity;
        }
        this.workingMemory = { ...this.workingMemory, ...parsedMemory };
        console.log("[Agent] Working Memory Updated (Speculative):", this.workingMemory);
      } catch (e) {
        console.warn("[Agent] Speculative slot filler failed to parse");
      }

      const sqlHints = sqlHintsResult.map((ex: any) => `Q: ${ex.question}\nSQL: ${ex.sql}`).join('\n\n');

      // 1.5 Table Routing (Pruning)
      this.addThought("Pruning schema for relevant tables...");
      const tableDescriptions = schemaData.tables.map((t: any) => `${t.table_name}: ${t.description}`).join('\n');

      let tableRouterPrompt = "";
      if (compiledPrograms['table_router']) {
        tableRouterPrompt = DSPyInterpreter.render(compiledPrograms['table_router'], {
          question: userQuery,
          table_descriptions: tableDescriptions
        });
      } else {
        tableRouterPrompt = PROMPTS.tableRouter(userQuery, tableDescriptions);
      }

      const tableRouterOutput = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: tableRouterPrompt }],
        jsonMode: true
      });

      const tableParsed = safeParseJSON(tableRouterOutput, ['selected_tables']);
      const selectedTables = Array.isArray(tableParsed.selected_tables) ? tableParsed.selected_tables : [];
      const prunedSchemaMd = generateSchemaMarkdown(schemaData, selectedTables);
      this.addThought(`Selected tables: ${selectedTables.join(', ')}`);

      // 2. ReAct Execution Loop
      let loopCount = 0;
      let observations = "";
      let finalSql = "";
      let lastData: any[] = [];

      this.addThought("Starting ReAct orchestrator loop...");

      while (loopCount < 3) {
        this.setState({ status: 'thinking' });

        let orchestratorPrompt = "";
        let isOptimized = false;

        // Use interpreter if artifact available, else fallback to template
        if (compiledPrograms['sql_generator']) {
          isOptimized = true;
          orchestratorPrompt = DSPyInterpreter.render(compiledPrograms['sql_generator'], {
            question: userQuery,
            db_schema: prunedSchemaMd,
            examples: sqlHints,
            previous_sql: observations.includes('SQL error') ? observations : "",
            error_message: observations.includes('SQL error') ? "A previous attempt failed. Correct the SQL." : ""
          });
        } else {
          orchestratorPrompt = PROMPTS.orchestrator(
            userQuery,
            observations,
            sqlHints,
            this.identity || "None",
            this.workingMemory,
            prunedSchemaMd
          );
          if (intent === 'league_rules') orchestratorPrompt += "\nNOTE: Focus only on league settings/rules tables.";
        }

        const step = await workerRequest(llmWorker, 'GENERATE', {
          messages: [{ role: 'user', content: orchestratorPrompt }],
          jsonMode: true
        });

        const stepParsed = safeParseJSON(step, ['reasoning', 'sql_query']);

        // Use unified schema fields
        const thought = stepParsed.reasoning;
        const action = stepParsed.sql_query;

        if (thought) this.addThought(`Thought: ${thought}`);

        if (action === 'Final Answer' || action === 'FinalAnswer') {
          this.addThought("Reached final conclusion.");
          break;
        }

        this.addThought(`Executing: ${action}`);
        this.setState({ status: 'executing' });

        try {
          // SQL Validation & Execution (Flywheel Phase 5.4 Assertions)
          const data = await workerRequest(dbWorker, 'EXEC_SQL', { sql: action });
          const dataRows = Array.isArray(data) ? data : (data.rows || []);

          if (dataRows.length === 0 && !action.toLowerCase().includes('limit')) {
            // Heuristic: if no data, maybe it's a specific filter issue? Add observation.
            observations += `\nAction: ${action}\nObservation: Query returned 0 rows. Verify filters/IDs.`;
          } else {
            lastData = dataRows;
            finalSql = action;
            observations += `\nAction: ${action}\nObservation: Success. Data sample: ${JSON.stringify(dataRows.slice(0, 3))}`;

            // If we have data, we can often stop here if the question is simple
            if (loopCount > 0) {
              this.addThought("Data acquired. Preparing final answer.");
              break;
            }
          }

          // Truncate observations to prevent prompt overflow
          observations = truncateObservations(observations);
        } catch (e: any) {
          // ASSERTION: Feed error back to LLM for self-correction
          this.addThought(`SQL Error detected: ${e.message}. Attempting self-correction...`);
          observations += `\nAction: ${action}\nObservation: SQL error: ${e.message}. Correct the SQL syntax or table names and try again.`;

          // Extend loop limit slightly if we hit an error early on
          if (loopCount < 2) loopCount--; // Effectively "retry" with more context
        }

        loopCount++;
      }

      // 4. Final Responder
      this.setState({ status: 'answering' });
      this.addThought("Synthesizing final answer... ");
      const dataStr = JSON.stringify(lastData.slice(0, 50)).substring(0, 3000);
      const historyStr = history.slice(-5).map(m => `${m.role}: ${m.content}`).join('\n');

      const answer = await workerRequest(llmWorker, 'GENERATE', {
        messages: [{ role: 'user', content: PROMPTS.responder(historyStr, dataStr) }],
        stream: true
      }, (chunk) => this.addThoughtChunk(chunk));

      this.setState({ status: 'idle' });

      // Log query for analysis
      this.lastQueryId = Logger.logQuery({
        userQuery,
        workingMemory: this.workingMemory,
        sqlGenerated: finalSql,
        dataRows: lastData.length,
        answer,
        durationMs: Date.now() - startTime,
        thoughtProcess: [...this.state.thoughts],
        tablesUsed: selectedTables || []
      });

      return { answer, data: lastData, sql: finalSql };

    } catch (err: any) {
      this.setState({ status: 'error', error: err.message });
      throw err;
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
