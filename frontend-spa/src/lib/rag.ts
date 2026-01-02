import { pipeline } from '@xenova/transformers';

let embedder: any = null;
let shotBank: any[] = [];

export async function initRAG() {
  if (embedder) return;

  // Load the embedding model (Quantized for browser)
  // 'Xenova/all-MiniLM-L6-v2' is a good balance of speed/quality
  embedder = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');

  // Load Shot Bank
  const res = await fetch('/assets/golden_dataset.json');
  shotBank = await res.json();

  // Pre-calculate embeddings for shot bank if not already done?
  // Doing it live for 2-3 examples is fast. But for the bank, better to do it once.
  // For this MVP, we will embed the bank on load (it's small).
  for (const shot of shotBank) {
    if (!shot.embedding) {
      const out = await embedder(shot.question, { pooling: 'mean', normalize: true });
      shot.embedding = out.data;
    }
  }
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
    `Example ${i+1}:\nQ: ${s.question}\nSQL: ${s.sql}`
  ).join('\n\n');
}
