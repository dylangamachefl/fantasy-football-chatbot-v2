# Comprehensive Architectural Review

**Date:** January 12, 2026
**Scope:** `apps/chat-app`, `suite/evaluation`, `suite/original-backend`
**Context:** Monorepo transition; optimizations for "Zero Server-Side Compute" implemented.

---

## 1. Web-Native ML Infrastructure Architect (Strategist)

### Findings
*   **✅ Improved**: `db.worker.ts` now correctly checks for OPFS existence before fetching the database, addressing the previous memory/bandwidth concern.
*   **✅ Improved**: `llm.worker.ts` includes a robust fallback mechanism (switching to `Phi-3.5` if `Qwen` fails), improving runtime resilience.
*   **⚠️ Critical Risk**: `rag.worker.ts` imports `@xenova/transformers` from a CDN (`cdn.jsdelivr.net`), despite the project having a local dependency in `package.json`. This introduces an external runtime dependency that could break offline capabilities or if the CDN is unreachable.
*   **⚠️ Hardcoded Configuration**: `agent.ts` contains placeholder credentials for Langfuse (`pk-lf-...`) and hardcoded addresses (`localhost:3000`). This will fail in a real deployment.

### Recommendations
*   **Dependency Management**: Update `rag.worker.ts` to use the local `import ... from '@xenova/transformers'` (resolved by Vite) instead of the CDN URL.
*   **Configuration**: Move Langfuse configuration to `import.meta.env` variables (e.g., `VITE_LANGFUSE_PUBLIC_KEY`) to support different environments.

---

## 2. Declarative AI Programming Specialist (Tactician)

### Findings
*   **❌ Persistent Issue**: The Prompt Pipeline remains disjointed. `prompts.ts` relies on manual porting ("Ported from backend...") from `dspy_signatures.py`. Any DSPy optimization performed in the `suite/` is not automatically propagated to the client.
*   **Logic Parity**: The logic in `agent.ts` (Query Enhancement -> Router -> SQL Gen) faithfully replicates the Python `workflow.py` logic, but it is a manual reimplementation. If the Python workflow changes (e.g., adding a new step), the TypeScript agent must be manually updated.

### Recommendations
*   **Automated Sync**: Implement a build script (in `suite/data-ops`) that compiles `dspy_signatures.py` into a JSON artifact, which `prompts.ts` implies or imports. This ensures the frontend uses exactly what the optimizer produced.

---

## 3. Relational Data Systems Engineer (Tactician)

### Findings
*   **Schema Handling**: `agent.ts` loads a static `schema.json`. The filtering logic (selecting only relevant tables) is implemented client-side, which is good for context window management.
*   **Data Ops**: The repository structure `suite/data-ops` suggests a move towards centralized data management, but the connection between `table_dictionary.csv` (source) and `schema.json` (artifact) still requires manual verification to ensure no drift.

### Recommendations
*   **CI/CD Validation**: Add a CI step that verifies `schema.json` matches the definitions in `table_dictionary.csv` to prevent "Schema Drift".

---

## 4. ML Evaluator & Quality Assurance Lead (Strategist)

### Findings
*   **✅ Major Milestone**: The "Evaluation Target" gap has been closed. `run_frontend_evals.py` now exists and tests the actual `apps/chat-app` using Playwright and "LLM-as-a-Judge" (Ollama).
*   **Observability Gap**: While the *App* sends traces to Langfuse (localhost), and the *Eval Script* logs grades, there is no automatic correlation. If a test fails in `run_frontend_evals.py`, you have to manually hunt for the corresponding trace in Langfuse using timestamps.
*   **Test Robustness**: The eval script relies on polling DOM elements (`.message-assistant`). If the UI class names change, the entire eval suite breaks.

### Recommendations
*   **Trace Correlation**: In `run_frontend_evals.py`, inject a specific `Trace-Id` or `Session-Id` header (or URL parameter) when launching the browser, so that the App can use it to initialize Langfuse. This would link the Playwright run to the Langfuse trace.
*   **Data Data-Attributes**: Update `apps/chat-app` components to use stable data attributes (e.g., `data-testid="assistant-message"`) instead of CSS classes for testing.

---

## Cross-Disciplinary Conflicts

*   **Performance vs. Observability**: The `agent.ts` instrumentation is heavy. Sending detailed traces (including full prompts and schema contexts) to an external observer (even localhost) might impact the "snappiness" of the local-first experience, especially on lower-end devices.

## Prioritized Refactor Backlog

1.  **[High - Infra] Fix RAG Dependency**: Switch `rag.worker.ts` to use local NPM package instead of CDN.
2.  **[High - Ops] Externalize Config**: Replace hardcoded Langfuse keys in `agent.ts` with environment variables.
3.  **[Medium - QA] Harden Evals**: Add `data-testid` attributes to the frontend and update `run_frontend_evals.py` to use them.
4.  **[Medium - AI] Prompt Pipeline Sync**: Create a script to generate `prompts.ts` from DSPy signatures.
