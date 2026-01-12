# Local SQL Agent (Client-Side SPA)

A fully client-side implementation of the SQL Agent, running entirely in the browser using WebAssembly and WebGPU. **Zero server-side compute required.**

## Features

- **Local LLM Inference**: Uses [WebLLM](https://webllm.mlc.ai/) (powered by WebGPU) to run `Qwen 2.5 (1.5B)` or `Phi 3.5` directly in the browser.
- **In-Browser Database**: Uses [SQLite WASM](https://sqlite.org/wasm) with Origin Private File System (OPFS) for high-performance, persistent SQL execution.
- **RAG System**: Uses [Transformers.js](https://huggingface.co/docs/transformers.js/) for client-side embedding generation and retrieval.
- **Agentic Workflow**: Implements a Reflexion loop (Generate -> Execute -> Error -> Retry) running in a Web Worker to keep the UI responsive.

## Prerequisites

- **Browser**: Google Chrome, Edge, or any browser with **WebGPU** support.
- **GPU**: A dedicated GPU is recommended, but modern integrated GPUs (e.g., Apple M-series) work well.
- **Node.js**: v18+ for building.

## Installation

1. Navigate to the `frontend-spa` directory:
   ```bash
   cd frontend-spa
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

## Running Locally

1. Start the development server:
   ```bash
   npm run dev
   ```

2. Open your browser to the URL shown (usually `http://localhost:5173`).

   > **Note**: The first time you load the model, it will download ~1-2GB of weights to your browser cache. Subsequent loads will be much faster.

## Build for Production

1. Build the assets:
   ```bash
   npm run build
   ```

2. Preview the build:
   ```bash
   npm run preview
   ```

## Architecture

- **`src/workers/llm.worker.ts`**: Handles the heavy lifting of the LLM inference in a separate thread to avoid freezing the UI.
- **`src/workers/db.worker.ts`**: Manages the SQLite database instance and executes queries.
- **`src/lib/agent.ts`**: Orchestrates the communication between the UI, the LLM worker, and the DB worker.
- **Assets**: Database (`llm_fantasy_data.db`) and schema files are loaded from `public/assets/` into the browser environment on startup.

## Troubleshooting

- **"WebGPU is not supported"**: Ensure you are using a compatible browser (Chrome/Edge) and that hardware acceleration is enabled.
- **Model Download Failures**: Ensure you have a stable internet connection for the initial download.
- **SharedArrayBuffer Errors**: This app requires specific security headers (`Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy`), which are configured in `vite.config.ts`. If deploying to a static host (like Vercel/Netlify), ensure these headers are set in the host configuration.
