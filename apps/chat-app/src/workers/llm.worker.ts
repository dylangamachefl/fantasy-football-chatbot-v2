import { CreateMLCEngine, MLCEngine, type InitProgressReport } from "@mlc-ai/web-llm";

let engine: MLCEngine | null = null;

import MODELS from '../config/models.json';

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
        if (payload.stream) {
          await generateStream(payload.messages, id, payload.jsonMode);
        } else {
          const { text, metadata } = await generate(payload.messages, payload.schema, payload.jsonMode);
          self.postMessage({ type: 'GENERATE_SUCCESS', id, payload: text, metadata });
        }
        break;

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error: any) {
    self.postMessage({ type: 'ERROR', id, error: error.message });
  }
};

let currentModelId = "";

async function initLLM(modelId: string) {
  currentModelId = modelId;
  const initProgressCallback = (report: InitProgressReport) => {
    self.postMessage({
      type: 'PROGRESS',
      payload: { text: report.text, progress: report.progress }
    });
  };

  try {
    console.log(`[LLM Worker] Initializing engine with model: ${modelId}`);
    engine = await CreateMLCEngine(modelId, { initProgressCallback });
    console.log(`[LLM Worker] Engine initialized successfully.`);
  } catch (error: any) {
    console.error(`[LLM Worker] Failed to load model ${modelId}: ${error.message}`);
    throw error;
  }
}

async function generate(messages: any[], _schema?: any, jsonMode: boolean = false) {
  if (!engine) throw new Error("Engine not initialized");

  const startTime = Date.now();
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

  const fullText = output.choices[0].message.content;
  return {
    text: fullText,
    metadata: {
      totalTime: Date.now() - startTime,
      modelUsed: currentModelId
    }
  };
}

async function generateStream(messages: any[], id: string, jsonMode: boolean = false) {
  if (!engine) throw new Error("Engine not initialized");

  const startTime = Date.now();
  let firstTokenTime = 0;

  const options: any = { temperature: 0.1 };
  if (jsonMode) options.response_format = { type: "json_object" };

  const asyncChunkGenerator: any = await engine.chat.completions.create({
    messages,
    stream: true,
    ...options
  });

  let fullText = "";
  for await (const chunk of asyncChunkGenerator) {
    if (!firstTokenTime) firstTokenTime = Date.now() - startTime;
    const text = chunk.choices[0]?.delta?.content || "";
    fullText += text;
    self.postMessage({ type: 'CHUNK', id, payload: text });
  }

  self.postMessage({
    type: 'GENERATE_SUCCESS',
    id,
    payload: fullText,
    metadata: {
      ttft: firstTokenTime,
      totalTime: Date.now() - startTime,
      modelUsed: currentModelId
    }
  });
}
