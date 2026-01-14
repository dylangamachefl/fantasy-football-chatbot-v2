# Technical Audit: Client-Side Text-to-SQL Agent

## 1. Structural Overview

### Project Topology
The repository operates as a **Monorepo** with three distinct components:
1.  **Client-Side SPA (`apps/chat-app`)**: The production-facing application. Built with React, Vite, and Tailwind CSS. It is designed to run entirely in the browser (Local-First).
2.  **Backend/Dev Suite (`suite/original-backend`)**: A Python-based backend (FastAPI, LangGraph) likely serving as a reference implementation or for offline optimization. It includes a "Sidecar" service for SQL execution.
3.  **Evaluation Suite (`suite/evaluation`)**: Python scripts for running quality evaluations against both the backend and frontend.

### Dependency Analysis
*   **Frontend**:
    *   **Core**: React 19, Vite 5.
    *   **AI/ML**: `@mlc-ai/web-llm` (LLM Inference), `@xenova/transformers` (Embeddings/RAG).
    *   **Data**: `@sqlite.org/sqlite-wasm` (SQL Engine).
    *   **Observation**: Dependencies are well-segregated. The use of Web Workers (`db.worker.ts`, `llm.worker.ts`, `rag.worker.ts`) is a critical architectural decision that prevents UI blocking during heavy inference tasks.

*   **Backend**: Standard Python AI stack (LangChain, LangGraph, DSPy, FastAPI).

## 2. Data Lifecycle & Infrastructure

### Data Ingestion
*   **Mechanism**: The frontend fetches a static SQLite database file (`fantasy_football_wide.db`) from the `/assets/` directory.
*   **Loading**: The `db.worker.ts` loads this file into the **Origin Private File System (OPFS)** via `sqlite-wasm`.
*   **Optimization**: The worker checks for the existence of the DB in OPFS before fetching, ensuring faster subsequent loads.

### Query Execution (The "Text-to-SQL" Path)
The execution pipeline is entirely client-side:
1.  **Input**: User types a natural language query.
2.  **Slot Filling**: `Agent` -> `llmWorker` extracts entities (Manager, Season) to update Working Memory.
3.  **Enhancement**: `llmWorker` rewrites the query using conversation history.
4.  **Retrieval (RAG)**: `ragWorker` embeds the query and retrieves similar SQL examples and "Lore" from JSON files.
5.  **Routing**: `llmWorker` selects relevant tables from the schema.
6.  **Generation**: `llmWorker` generates SQL based on the filtered schema and examples.
7.  **Validation**: `db.worker.ts` runs `EXPLAIN QUERY PLAN` to validate syntax.
8.  **Execution**: `db.worker.ts` executes the SQL against the OPFS database.
9.  **Response**: `llmWorker` synthesizes a natural language answer from the data.

### Persistence
*   **Database**: Persisted in OPFS (Browser Storage).
*   **Session State**: Ephemeral (React State). Reloading the page clears chat history.
*   **Agent State**: Ephemeral (In-memory `Agent` instance).

## 3. Architectural Patterns & Integrity

### Design Patterns
*   **Worker Pattern**: Heavy computational tasks (LLM, DB, RAG) are correctly offloaded to Web Workers.
*   **Observer Pattern**: The `Agent` class accepts a callback to update the UI state (`onStateChange`).

### Coupling & Cohesion
*   **Coupling**: The `Agent` class is tightly coupled to the specific worker file paths and message protocols.
*   **Cohesion**: The separation of concerns is generally good, with distinct workers for distinct domains (DB vs LLM vs RAG).

### Anti-Patterns
*   **Build Fragility**: The `rag.worker.ts` file uses a direct HTTPS import (`from 'https://cdn.jsdelivr.net...'`). This causes the TypeScript build (`npm run build`) to fail because standard TypeScript does not support remote URL imports. This breaks the CI/CD pipeline.
*   **Hardcoded Models**: Model IDs in `llm.worker.ts` are hardcoded.

## 4. Non-Functional Requirements

### Performance
*   **Bottlenecks**:
    *   **Initial Load**: Downloading the LLM weights (~2GB+) is a significant barrier to entry.
    *   **Inference**: Browser-based inference is computationally expensive and battery-draining on mobile devices.
*   **Efficacy**: Once loaded, the system is responsive for SQL execution (SQLite WASM is very fast).

### Security & Privacy
*   **Data Privacy**: Excellent. All data processing happens locally in the user's browser. No user data is sent to a server.
*   **Security**: Low attack surface. SQL injection is contained within the client's sandbox.

### Error Handling
*   **Resilience**: The Agent implements a "Reflexion" loop (retrying SQL generation upon error) which improves robustness.
*   **Fallback**: The LLM worker attempts to fall back to a smaller model if the primary one fails to load, though the logic is basic.

## 5. Documentation & Maintainability

### Legibility
*   The code is clean and uses modern TypeScript features.
*   The logic flow in `Agent.processQuery` is complex but readable.

### Extensibility
*   **Adding Sports/Leagues**: Difficult. The schema, database file, and RAG datasets are hardcoded assets. Supporting a new league would require replacing these files and potentially updating the RAG logic.
*   **Switching LLMs**: Requires code changes in `llm.worker.ts`.

### Build Status
*   **Current Status**: **FAILING**.
*   **Reason**: `src/workers/rag.worker.ts` contains an HTTPS import which is rejected by `tsc`.
*   **Recommendation**: Replace the CDN import with a local npm package install of `@xenova/transformers` or configure the bundler/compiler to ignore this file during type checking.
