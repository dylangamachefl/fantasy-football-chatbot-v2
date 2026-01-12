# 💻 Chat App: Client-Side Fantasy Football Agent

This is the user-facing application for the Fantasy Football Chatbot. It is built with **React**, **Vite**, and **TailwindCSS**, and it runs entirely client-side using local LLM inference.

## ⚡ Key Technologies
- **@mlc-ai/web-llm**: Local browser-based inference for Qwen-2.5.
- **SQLite-WASM**: In-memory database execution for league stats.
- **Transformers.js**: Local embedding generation for RAG (Retrieval-Augmented Generation).
- **Langfuse Web SDK**: Optional tracing to the local observability suite.

## 🛠 Setup

1. **Install Dependencies**
   ```bash
   npm install
   ```

2. **Run Development Server**
   ```bash
   npm run dev
   ```

3. **Production Build**
   ```bash
   npm run build
   ```
   *The output in `dist/` is a pure static site that can be deployed to any host (Vercel, Netlify, Github Pages).*

## 🧩 Architecture

The agent logic is contained in `src/lib/agent.ts`. It follows a multi-stage pipeline:
1. **Query Enhancement**: Context resolution and nickname normalization.
2. **Table Routing**: Dynamic schema filtering to manage 100+ tables.
3. **Execution**: Running generated SQL against the local `llm_fantasy_data.db`.
4. **Response**: Natural language answer synthesis.

## 🛠 Observability
When running in development, the app attempts to send traces to `http://localhost:3000` (the **Observability Suite**). Ensure the Docker stack in `../../suite/observability` is running to view these traces.

## 📂 Assets
The app uses assets (Schema, Golden Dataset, DB) located in `public/assets`. In a production workflow, these are synced from the root `shared/` directory.
