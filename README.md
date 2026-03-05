# 🏈 Fantasy Football Chatbot V2: Monorepo (WIP)

A sophisticated, **100% client-side** conversational AI agent designed for advanced SQL analysis on fantasy football data. This project demonstrates high-performance **On-Device LLM orchestration** through a **Teacher-Student Flywheel** architecture, allowing for continuous prompt optimization without backend overhead.

> [!IMPORTANT]
> **Showcase for Technical Recruiters**: This project highlights expertise in browser-based AI (WebLLM/WASM), local data engineering (SQLite WASM), and multi-agentic orchestration.

## 📂 Project Structure

```
fantasy-football-chatbot-v2/
├── apps/
│   └── chat-app/             # 💻 The Application (100% Client-Side React)
├── suite/                    # 🛠 The Developer Suite (Local-Only)
│   ├── dashboard/            # 🚀 Sidecar "Mission Control" UI
│   ├── evaluation/           # 🤖 DSPy scripts & "Offline" optimization
│   ├── data-ops/             # 🧹 Dataset management & generation
│   └── observability/        # 📊 Legacy Langfuse traces (Docker)
├── shared/                   # 📦 Shared Assets (Schema, Golden Data, DB)
└── README.md
```

## 🛠️ Engineering Highlights & Skills

This monorepo serves as a demonstration of several advanced software engineering domains:

- **Browser-Based AI Orchestration**: Utilizing `@mlc-ai/web-llm` and WASM to run multi-billion parameter models (Qwen 7B) directly in the browser with high performance.
- **D-ST Architecture**: Implementing a "Decoupled Student-Teacher" loop. The "Student" (Chat App) remains ultra-lightweight, while a "Teacher" model (local Ollama) handles computationally intensive labeling and optimization tasks.
- **Dynamic Context Pruning**: Advanced RAG patterns involving multi-step intent classification and semantic table routing to handle complex, 100+ table schemas within the limited context windows of browser LLMs.
- **Local Observability & Data-Ops**: Building custom logging and dataset curation tools that maintain data privacy and zero-latency feedback loops.

## 🧬 Tech Stack

- **Frontend**: React, Vite, TypeScript, Vanilla CSS.
- **AI Core**: WebLLM (MLC-LLM), WASM, DSPy (Python).
- **Database**: SQLite (local bridge), SQLite WASM (future-mapping).
- **Developer Tools**: Ollama (Teacher), Python (Data-ops/Evaluation).

## 🚀 Getting Started

### 1. Run the Application
The chat application runs entirely in your browser using local inference (no backend API needed).

```bash
cd apps/chat-app
npm install
npm run dev
```

### 2. The Local Data Flywheel
The system improves itself through a feedback loop:
1. **Log & Extract**: User feedback (👍/👎) is logged locally. Failed queries are extracted for the Teacher.
2. **Teacher Labeling**: A "Teacher" model (Ollama/Qwen) generates reasoning and correct SQL for failures.
3. **DSPy Optimization**: The `suite/evaluation` tools compile new, optimized prompts.
4. **Deploy**: Optimized prompts are exported back to the browser-based Student (Chat App).

### 3. Developer Dashboard
Run the sidecar dashboard to manage datasets and visualize evaluations:
```bash
cd suite/dashboard
npm install
npm run dev
```

## ⚡ Key Features
- **Teacher-Student Flywheel**: Continuous improvement loop using local "Teacher" models to train smaller "Student" models for production.
- **On-Device Inference**: Private, zero-latency, and zero-cost analysis powered by WASM.
- **SQL Intelligence**: Automated SQL generation for complex relational schemas with recursive error reflection.
- **Mission Control UI**: A dedicated "Sidecar" developer dashboard for real-time evaluation and dataset management.

## 📖 Documentation
- [App README](apps/chat-app/README.md)
- [Suite Documentation](suite/README.md) (coming soon)
- [Improvement Walkthrough](https://example.com) (refer to `.gemini/` artifacts for detail)
