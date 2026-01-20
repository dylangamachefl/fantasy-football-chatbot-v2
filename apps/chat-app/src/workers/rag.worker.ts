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
        console.log(`[RAG Worker] Starting retrieval for collection: ${payload.collection}, query: ${payload.query}`);
        const results = await retrieve(payload.query, payload.collection, payload.k);
        console.log('[RAG Worker] Retrieval complete, sending results');
        self.postMessage({ type: 'RETRIEVE_SUCCESS', id, payload: results });
        break;

      case 'RETRIEVE_BATCH':
        console.log(`[RAG Worker] Starting batch retrieval for ${payload.length} requests`);
        const batchResults = await Promise.all(payload.map((req: any) =>
          retrieve(req.query, req.collection, req.k)
        ));
        console.log('[RAG Worker] Batch retrieval complete');
        self.postMessage({ type: 'RETRIEVE_BATCH_SUCCESS', id, payload: batchResults });
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
    embedder = await pipeline('feature-extraction', modelId);
    console.log("[RAG Worker] Embedder initialized successfully.");
  } catch (error) {
    console.error("[RAG Worker] Failed to initialize embedder:", error);
    throw error;
  }

  // Load Banks
  await Promise.all([
    loadBank('/assets/golden_dataset.json', 'SQL')
  ]);
}

async function loadBank(url: string, type: 'SQL' | 'LORE') {
  try {
    console.log(`[RAG Worker] Fetching ${type} bank from ${url}...`);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch ${type} bank: ${res.statusText}`);
    const data = await res.json();

    if (type === 'SQL') shotBank = data;

    console.log(`[RAG Worker] Loaded ${data.length} items for ${type} bank.`);

    // Pre-calculate embeddings
    const itemsToEmbed = data.filter((item: any) => !item.embedding);
    if (itemsToEmbed.length > 0) {
      const texts = itemsToEmbed.map((item: any) =>
        item.question
      );

      try {
        console.log(`[RAG Worker] Batch embedding ${texts.length} items for ${type}...`);
        const out = await embedder(texts, { pooling: 'mean', normalize: true });
        const batchSize = out.dims[0];
        const embDim = out.dims[1];

        for (let i = 0; i < batchSize; i++) {
          const start = i * embDim;
          const end = start + embDim;
          itemsToEmbed[i].embedding = Array.from(out.data.slice(start, end));
        }
      } catch (e) {
        console.warn(`[RAG Worker] Batch embedding failed, falling back to concurrent execution:`, e);
        await Promise.all(itemsToEmbed.map(async (item: any, i: number) => {
          const out = await embedder(texts[i], { pooling: 'mean', normalize: true });
          item.embedding = Array.from(out.data);
        }));
      }
    } else {
      console.log(`[RAG Worker] ${type} bank already contains embeddings. Skipping calculation.`);
    }
    console.log(`[RAG Worker] ${type} bank ready.`);
  } catch (error) {
    console.error(`[RAG Worker] Failed to load ${type} bank:`, error);
    throw error;
  }
}

async function retrieve(query: string, collection: 'SQL', k: number = 3): Promise<any[]> {
  if (!embedder) throw new Error("Embedder not ready");
  if (!query || query.trim() === '') {
    console.warn(`[RAG Worker] Empty query received for ${collection}, returning empty results`);
    return [];
  }

  const bank = shotBank;
  if (bank.length === 0) return [];

  const out = await embedder(query, { pooling: 'mean', normalize: true });
  const queryEmb = out.data;

  // Cosine similarity
  const scored = bank.map(item => {
    let dot = 0;
    for (let i = 0; i < queryEmb.length; i++) {
      dot += queryEmb[i] * item.embedding[i];
    }
    return { ...item, score: dot };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k);
}
