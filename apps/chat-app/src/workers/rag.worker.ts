import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';

// Configure env to use local models
env.allowLocalModels = true;
env.allowRemoteModels = false;
env.localModelPath = '/models/';

let embedder: any = null;
let shotBank: any[] = [];

self.onmessage = async (e: MessageEvent) => {
  const { type, payload, id } = e.data;

  try {
    switch (type) {
      case 'INIT_RAG':
        await initRAG();
        self.postMessage({ type: 'INIT_SUCCESS', id });
        break;

      case 'RETRIEVE':
        const results = await retrieveExamples(payload.query, payload.k);
        self.postMessage({ type: 'RETRIEVE_SUCCESS', id, payload: results });
        break;

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error: any) {
    self.postMessage({ type: 'ERROR', id, error: error.message || String(error) });
  }
};

async function initRAG() {
  if (embedder) return;

  try {
    const modelId = 'Xenova/all-MiniLM-L6-v2';
    console.log(`[RAG Worker] Initializing with local model: ${modelId}`);

    embedder = await pipeline('feature-extraction', modelId);
    console.log("[RAG Worker] Embedder initialized.");
  } catch (error) {
    console.error("[RAG Worker] Failed to initialize embedder:", error);
    throw error;
  }

  // Load Shot Bank
  try {
    const res = await fetch('/assets/golden_dataset.json');
    if (!res.ok) throw new Error(`Failed to fetch dataset: ${res.statusText}`);
    shotBank = await res.json();
    console.log(`[RAG Worker] Loaded ${shotBank.length} examples.`);
  } catch (error) {
    console.error("[RAG Worker] Failed to load shot bank:", error);
    throw error;
  }

  // Pre-calculate embeddings for shot bank
  console.log("[RAG Worker] Embedding shot bank...");
  for (const shot of shotBank) {
    if (!shot.embedding) {
      const out = await embedder(shot.question, { pooling: 'mean', normalize: true });
      shot.embedding = Array.from(out.data);
    }
  }
  console.log("[RAG Worker] Shot bank ready.");
}

async function retrieveExamples(query: string, k: number = 3): Promise<string> {
  if (!embedder || shotBank.length === 0) return "";

  const out = await embedder(query, { pooling: 'mean', normalize: true });
  const queryEmb = out.data;

  // Cosine similarity
  const scored = shotBank.map(shot => {
    let dot = 0;
    for (let i = 0; i < queryEmb.length; i++) {
      dot += queryEmb[i] * shot.embedding[i];
    }
    return { ...shot, score: dot };
  });

  scored.sort((a, b) => b.score - a.score);
  const topK = scored.slice(0, k);

  return topK.map((s, i) =>
    `Example ${i + 1}:\nQ: ${s.question}\nSQL: ${s.sql}`
  ).join('\n\n');
}
