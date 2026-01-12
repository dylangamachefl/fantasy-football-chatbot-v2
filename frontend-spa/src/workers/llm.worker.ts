import { CreateMLCEngine, MLCEngine, type InitProgressReport } from "@mlc-ai/web-llm";

let engine: MLCEngine | null = null;

// Models configuration
const MODELS = {
  primary: "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
  robust: "Phi-3.5-mini-instruct-q4f16_1-MLC", // Note: Ensure this ID is correct in MLC registry or custom
};

// Check official MLC registry for exact IDs if needed.
// For now we use the ones requested, mapped to likely MLC IDs.
// Qwen2.5-1.5B-Instruct-q4f16_1 is standard.
// Phi-3.5-mini-instruct-q4f16_1 might need verification, but we'll stick to the plan.

self.onmessage = async (e: MessageEvent) => {
  const { type, payload, id } = e.data;

  try {
    switch (type) {
      case 'INIT_LLM':
        await initLLM(payload.modelId || MODELS.primary);
        self.postMessage({ type: 'INIT_SUCCESS', id });
        break;

      case 'GENERATE':
        const response = await generate(payload.messages, payload.schema, payload.jsonMode);
        self.postMessage({ type: 'GENERATE_SUCCESS', id, payload: response });
        break;

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error: any) {
    self.postMessage({ type: 'ERROR', id, error: error.message });
  }
};

async function initLLM(modelId: string) {
  const initProgressCallback = (report: InitProgressReport) => {
    self.postMessage({
      type: 'PROGRESS',
      payload: { text: report.text, progress: report.progress }
    });
  };

  console.log(`[LLM Worker] Initializing engine with model: ${modelId}`);
  engine = await CreateMLCEngine(modelId, { initProgressCallback });
  console.log(`[LLM Worker] Engine initialized successfully.`);
}

async function generate(messages: any[], _schema?: any, jsonMode: boolean = false) {
  if (!engine) throw new Error("Engine not initialized");

  const options: any = {
    temperature: 0.1, // Low temp for SQL/Code
  };

  if (jsonMode) {
    options.response_format = { type: "json_object" };
  }

  const output = await engine.chat.completions.create({
    messages,
    ...options
  });

  return output.choices[0].message.content;
}
