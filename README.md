# 🏈 Fantasy Football Chatbot V2: Monorepo

A modern, "local-first" conversational AI agent that performs advanced SQL analysis on your league history. 

This repository is organized as a **Monorepo** to separate the user-facing application from the local developer tools used for evaluation and observability.

## 📂 Project Structure

```
fantasy-football-chatbot-v2/
├── apps/
│   └── chat-app/             # 💻 The Application (100% Client-Side)
│       ├── src/              # React + Vite + WebLLM (Qwen)
│       └── public/           # Static assets
├── suite/                    # 🛠 The Developer Suite (Local-Only)
│   ├── evaluation/           # DSPy scripts & "Offline" optimization
│   └── observability/        # Historical local Langfuse (Docker)
├── shared/                   # 📦 Shared Assets
│   ├── schema.json           # Database context
│   ├── golden_dataset.json   # SQL examples for RAG
│   └── llm_fantasy_data.db   # Local SQLite league data
└── README.md
```

## 🚀 Getting Started

### 1. Run the Application
The chat application runs entirely in your browser using local inference (no backend API needed).

```bash
cd apps/chat-app
npm install
npm run dev
```

### 2. Observability (Langfuse Cloud)
Traces and evaluation results are now unified on **Langfuse Cloud**. 

- **UI**: [https://cloud.langfuse.com](https://cloud.langfuse.com)
- **Local Suite**: The Docker stack in `suite/observability` is legacy and can be shut down.

### 3. Evaluate & Optimize
Use the tools in `suite/evaluation` to run "offline" benchmarks against your golden dataset and optimize the system prompts for better accuracy.

## ⚡ Key Features
- **Local Inference**: Powered by `@mlc-ai/web-llm` for private, zero-cost analysis.
- **Dynamic Routing**: Automatically filters a massive schema (100+ tables) to only the relevant context for each query.
- **Defensive Design**: Streaming thoughts, fuzzy name matching, and robust SQL fallbacks.
- **D-ST Architecture**: Decoupled application logic from the evaluation data-ops layer.

## 📖 Documentation
- [App README](apps/chat-app/README.md)
- [Suite Documentation](suite/README.md) (coming soon)
- [Improvement Walkthrough](https://example.com) (refer to `.gemini/` artifacts for detail)
