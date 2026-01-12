# Comprehensive Architectural Review

**Date:** March 15, 2025
**Scope:** `apps/chat-app` (Frontend), `suite/original-backend` (Backend), `suite/evaluation` (Evals)
**Reviewers:** The Council of Experts (Web-Native Architect, Declarative AI Specialist, Data Systems Engineer, QA Lead)

---

## 1. Web-Native ML Infrastructure Architect (Strategist)

### Findings
*   **Runtime Stability:** The `db.worker.ts` loads the entire `llm_fantasy_data.db` into memory (`arrayBuffer`) and re-imports it into OPFS on *every* initialization. This is a significant memory spike and performance bottleneck for large databases.
*   **Resilience:** The `llm.worker.ts` hardcodes the model ID (`Qwen2.5-1.5B`) and lacks error handling. If the WebGPU context fails or the model fails to load (e.g., VRAM limits), the worker crashes silently or emits a generic error, with no fallback to a smaller model (like `Phi-3.5`).
*   **Configuration:** `vite.config.ts` correctly sets the `Cross-Origin-Embedder-Policy` and `Cross-Origin-Opener-Policy` headers required for `sqlite-wasm` and `WebGPU` SharedArrayBuffer support.
*   **Architecture:** The "Zero server-side compute" goal is respected, but the logic in `agent.ts` duplicates the Python backend's state machine, increasing maintenance burden.

### Recommendations
*   **Optimization:** Modify `db.worker.ts` to check if the DB exists in OPFS before fetching.
*   **Reliability:** Implement a "Robust Mode" fallback in `agent.ts` or `llm.worker.ts` that switches to `Phi-3.5` if `Qwen` fails to load.

---

## 2. Declarative AI Programming Specialist (Tactician)

### Findings
*   **Prompt Pipeline:** The `suite/original-backend` uses `DSPy` with clear signatures (`dspy_signatures.py`). However, the production frontend (`apps/chat-app`) uses **manual string interpolation** in `prompts.ts`.
*   **Optimization Gap:** While `dspy_config.py` has logic to load an "Optimized Program" from a registry, there is no active "Optimizer Loop" (like MIPRO) running to improve these prompts based on feedback. The prompts are effectively static.
*   **Logic Duplication:** The sophisticated "Reflexion" loop (Generate -> Execute -> Catch Error -> Retry) is well-implemented in Python (`workflow.py`) and manually replicated in TypeScript (`agent.ts`). Any algorithmic improvement in Python must be manually ported to TS.

### Recommendations
*   **Unification:** Create a build step or shared JSON schema that allows the Frontend to consume the *exact same* prompts/signatures as the Backend, or use a JS-compatible DSPy runtime.

---

## 3. Relational Data Systems Engineer (Tactician)

### Findings
*   **Schema Drift:** The backend constructs schema strings from `data/table_dictionary.csv`. The frontend loads `assets/schema.json`. These two sources are not synchronized, leading to potential "Schema Drift" where the AI hallucinates columns that exist in one definition but not the other.
*   **SQL Generation:** The `SafeSQLQueryTool` in the backend sidecar works well, but the frontend's `sqlite-wasm` implementation is completely separate. The `agent.ts` logic injects the *entire* schema into the prompt context, which scales poorly as the database grows.
*   **Validation:** There is no "Dry Run" or syntax validation step before execution in the frontend, relying entirely on SQLite's error messages for the Reflexion loop.

### Recommendations
*   **Single Source of Truth:** Generate `schema.json` directly from the `table_dictionary.csv` (or vice-versa) during the build process.

---

## 4. ML Evaluator & Quality Assurance Lead (Strategist)

### Findings
*   **CRITICAL GAP - The Evaluation Target:** The current evaluation suite (`run_conversation_evals.py`) runs against the **Python Backend**. However, the production application is the **TypeScript SPA**.
    *   **Impact:** Improvements measured in the evals *do not* translate to production because they test a different codebase (Python `workflow.py` vs TS `agent.ts`). The production app is effectively untested by the automated suite.
*   **Metric Validity:** The "LLM-as-a-Judge" uses `Gemini-2.5-Flash-Lite` with a simple "CORRECT/INCORRECT" rubric. It does not use the granular metrics (Reasoning Quality, SQL Syntax, Answer Fidelity) available in DSPy.
*   **Test Coverage:** Evals cover the "Happy Path" and basic retrieval. They do not test client-side specific failure modes (e.g., WebGPU OOM, OPFS corruption).

### Recommendations
*   **Highest Priority:** Create a **Frontend Evaluation Harness** using Playwright/Selenium that runs the actual `apps/chat-app` against the test set. This is the only way to measure production quality.

---

## Prioritized Refactor Backlog

1.  **[High - QA] Align Evaluation Target:** Create `evals/run_frontend_evals.py` to test the TypeScript SPA.
2.  **[High - Infra] Optimize DB Loading:** Fix `db.worker.ts` to prevent re-downloading/re-importing the DB on every page load.
3.  **[Medium - AI] Unify Prompts:** Standardize prompt definitions between Python and TypeScript to prevent logic drift.
4.  **[Medium - Infra] Robust LLM Fallback:** Add error handling to `llm.worker.ts` to handle WebGPU failures gracefully.
