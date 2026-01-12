// Initial configuration
let embedder: any = null;
let shotBank: any[] = [];

export async function initRAG() {
  if (embedder) return;

  // Access the CDN-loaded instance from window.transformers
  let transformers = (window as any).transformers;
  if (!transformers) {
    console.log("[RAG] Waiting for Transformers.js...");
    await new Promise(r => setTimeout(r, 500));
    transformers = (window as any).transformers;
  }

  if (!transformers) {
    throw new Error("Transformers.js failed to load. Check network/index.html.");
  }

  const { pipeline, env } = transformers;

  // IMPORTANT: Use local models from /public/models
  env.allowLocalModels = true;
  env.allowRemoteModels = false;
  env.localModelPath = '/models/';

  try {
    const modelId = 'Xenova/all-MiniLM-L6-v2';
    console.log(`[RAG] Initializing with local model: ${modelId}`);

    // Load the embedding model (using local files from /public/models/)
    try {
      embedder = await pipeline('feature-extraction', modelId);
      console.log("[RAG] Embedder initialized successfully from local files.");
    } catch (innerErr: any) {
      console.error("[RAG] Transformers.js pipeline failed:", innerErr.message);
      throw innerErr;
    }
  } catch (error) {
    console.error("[RAG] Failed to initialize RAG embedder core:", error);
    throw error;
  }

  // Load Shot Bank
  const res = await fetch('/assets/golden_dataset.json');
  shotBank = await res.json();

  // Pre-calculate embeddings for shot bank
  console.log("[RAG] Embedding shot bank...");
  for (const shot of shotBank) {
    if (!shot.embedding) {
      const out = await embedder(shot.question, { pooling: 'mean', normalize: true });
      shot.embedding = Array.from(out.data); // Ensure it's a standard array
    }
  }
  console.log("[RAG] Shot bank ready.");
}

export async function retrieveExamples(query: string, k: number = 3): Promise<string> {
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
