import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';

// Configure env - CDN version handles ONNX Runtime better in worker context
env.allowLocalModels = false;
env.allowRemoteModels = true;

let embedder: any = null;
let shotBank: any[] = [];

self.onmessage = async (e: MessageEvent) => {
  const { type, payload, id } = e.data;
  console.log(`[RAG Worker] Received message: ${type}`);

  try {
    switch (type) {
      case 'INIT_RAG':
        console.log('[RAG Worker] Starting initialization...');
        await initRAG();
        self.postMessage({ type: 'INIT_SUCCESS', id });
        break;

      case 'RETRIEVE':
        console.log('[RAG Worker] Starting retrieval for query:', payload.query);
        const results = await retrieveExamples(payload.query, payload.k);
        console.log('[RAG Worker] Retrieval complete, sending results');
        self.postMessage({ type: 'RETRIEVE_SUCCESS', id, payload: results });
        break;

      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error: any) {
    console.error('[RAG Worker] Error:', error);
    self.postMessage({ type: 'ERROR', id, error: error.message || String(error) });
  }
};

async function initRAG() {
  if (embedder) return;

  try {
    const modelId = 'Xenova/all-MiniLM-L6-v2';
    console.log(`[RAG Worker] Initializing with local model: ${modelId}`);
    console.log(`[RAG Worker] Starting model download/load from HuggingFace...`);

    embedder = await pipeline('feature-extraction', modelId);
    console.log("[RAG Worker] Embedder initialized successfully.");
  } catch (error) {
    console.error("[RAG Worker] Failed to initialize embedder:", error);
    throw error;
  }

  // Load Shot Bank
  try {
    console.log("[RAG Worker] Fetching golden dataset...");
    const res = await fetch('/assets/golden_dataset.json');
    if (!res.ok) throw new Error(`Failed to fetch dataset: ${res.statusText}`);
    shotBank = await res.json();
    console.log(`[RAG Worker] Loaded ${shotBank.length} examples from golden dataset.`);
  } catch (error) {
    console.error("[RAG Worker] Failed to load shot bank:", error);
    throw error;
  }

  // Pre-calculate embeddings for shot bank
  console.log("[RAG Worker] Pre-calculating embeddings for shot bank...");
  let processed = 0;
  for (const shot of shotBank) {
    if (!shot.embedding) {
      const out = await embedder(shot.question, { pooling: 'mean', normalize: true });
      shot.embedding = Array.from(out.data);
      processed++;

      // Log progress every 10 examples
      if (processed % 10 === 0 || processed === shotBank.length) {
        console.log(`[RAG Worker] Embedded ${processed}/${shotBank.length} examples...`);
      }
    }
  }
  console.log("[RAG Worker] Shot bank ready. All embeddings pre-calculated.");
}

async function retrieveExamples(query: string, k: number = 3): Promise<string> {
  if (!embedder || shotBank.length === 0) {
    console.log('[RAG Worker] Embedder or shot bank not ready, returning empty');
    return "";
  }

  console.log('[RAG Worker] Generating embedding for query...');
  const out = await embedder(query, { pooling: 'mean', normalize: true });
  const queryEmb = out.data;
  console.log('[RAG Worker] Query embedding generated, calculating similarities...');

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
  console.log(`[RAG Worker] Found top ${topK.length} examples`);

  return topK.map((s, i) =>
    `Example ${i + 1}:\nQ: ${s.question}\nSQL: ${s.sql}`
  ).join('\n\n');
}
