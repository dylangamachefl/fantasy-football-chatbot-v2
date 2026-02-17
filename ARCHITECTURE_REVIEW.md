# AI Architecture Review Report

**Date:** 2026-02-17
**Scope:** Full system review — browser agent pipeline, DSPy optimization flywheel, golden dataset, worker layer, data operations tooling

---

## Executive Summary

The system implements a sophisticated browser-first agentic architecture with a teacher-student flywheel for continuous improvement. The core design — ReAct loop with DSPy optimization, local inference via WebLLM, and HITL curation — is sound. However, there are several critical issues that will undermine the flywheel's effectiveness until addressed. The most impactful are: train/test data leakage in the evaluation pipeline, dual incompatible schemas in the golden dataset, and overly simplistic DSPy metrics that can't guide optimization.

---

## CRITICAL Issues

### 1. Train/Test Data Leakage in DSPy Pipeline

`optimize_prompts.py` loads the full golden dataset for BootstrapFewShot training. `benchmark_optimized.py` then evaluates on `golden_data[:10]` — the first 10 entries of the same file. `judge_results.py` similarly evaluates on data that overlaps with training.

**Files:**
- `suite/evaluation/optimize_prompts.py:63-84`
- `suite/evaluation/benchmark_optimized.py:56`
- `suite/evaluation/judge_results.py:41-42`

**Impact:** Reported accuracy is meaningless. Could show 90%+ while actual generalization is 50%.

**Fix:** Split golden_dataset.json into train (80%), val (10%), test (10%). Optimize on train, tune on val, report on test.

### 2. Golden Dataset Has Two Incompatible Schemas

~120 entries with two conflicting structures:

- **Format A (~50 entries):** `question`, `reasoning`, `intent`, `category`, `selected_tables`, `sql`, `answer`
- **Format B (~70 entries):** `question`, `sql`, `tables_used`, `category`, `answer` — missing `intent`, `reasoning`; uses `tables_used` instead of `selected_tables`

**Impact:**
- ~60% of entries lack `intent` — IntentRouter trains on only ~40% of data
- Field name mismatch (`selected_tables` vs `tables_used`) causes silent failures
- Missing `reasoning` degrades RAG embedding quality
- Answer format inconsistency (`{{field_name}}` vs `[Result]` vs literal) breaks judge evaluation

**Fix:** Standardize all entries to Format A during golden dataset validation pass.

### 3. DSPy Metrics Too Simplistic for Optimization

- **`intent_metric`:** Exact string match — no partial credit, no alias handling
- **`table_metric`:** Set equality — selecting 3/4 correct tables = 0% score
- **`validate_sql`:** Whitespace-normalized string comparison — semantically equivalent SQL fails

**Impact:** BootstrapFewShot gets almost no gradient signal. Metrics actively mislead optimization into memorizing exact strings.

**Fix:** Intent → canonicalize + exact match. Tables → F1/Jaccard score. SQL → AST comparison via sqlglot or execution-based comparison.

---

## HIGH Issues

### 4. Inconsistent Output Schemas Between Base Prompts and DSPy Artifacts

Base prompts produce `{ "thought", "action" }`. DSPy artifacts produce `{ "reasoning", "sql_query" }`. Reconciled in `agent.ts:366-367` with fallback chains.

**Impact:** Student model must learn two output schemas. DSPy optimizes against one but inference may use the other.

**Fix:** Standardize field names across DSPy signatures and base prompts.

### 5. Column Name Inconsistency (owner_name vs manager_name)

`schema.json` uses `manager_name` in some tables, `owner_name` in others. Golden dataset queries use both. Prompt template hardcodes `owner_name`.

**Impact:** Conflicting training signal; SQL errors that waste ReAct iterations.

**Fix:** Audit actual DB schema, pick one convention, update everywhere.

### 6. No JSON Parse Recovery in Agent Pipeline

`agent.ts` calls `JSON.parse()` without try-catch at lines 215, 318, 363.

**Impact:** 1.5B WASM model will produce malformed JSON regularly; entire query crashes.

**Fix:** Wrap in try-catch with regex fallback extraction and retry.

### 7. RAG Worker Never Loads LORE Bank

`rag.worker.ts:62` only loads SQL collection. LORE collection type-defined but never implemented.

**Impact:** League history queries get no few-shot examples.

### 8. Deprecated LangChain API in Judge + Fragile Grade Parsing

`judge_results.py` uses deprecated `QAEvalChain`. String matching counts "PARTIALLY CORRECT" as correct.

**Fix:** Switch to structured JSON judge output.

### 9. Template Literal Injection in Export Pipeline

`export_prompts.py:59-67` injects strings into TypeScript template literals without escaping backticks or `${}`.

**Impact:** Deployment pipeline bomb if any demo contains special characters.

**Fix:** Escape before injection, or switch to JSON file imports.

---

## MEDIUM Issues

### 10. Unbounded Observation String in ReAct Loop

`agent.ts:324` concatenates SQL results/errors per iteration. By iteration 3, can be 5KB+ injected into prompt.

**Fix:** Truncate to fixed token budget; keep most recent observation + summary.

### 11. `tablesUsed` Always Empty in Logs

`agent.ts:432` logs `tablesUsed: []`. Table router output never flows to logger.

**Impact:** Flywheel can't learn table-query associations; dashboard blind spot.

### 12. No Prompt Version Tracking in Logs

Logger records query data but not which prompt version or artifact produced the response.

**Impact:** Can't attribute improvements/regressions to specific changes.

### 13. Dead Code in Prompts

- `OPTIMIZED_SQL_EXAMPLES`/`OPTIMIZED_SQL_INSTRUCTION` at `prompts.ts:48-49` — empty, never populated
- `queryEnhancer` at `prompts.ts:105-129` — defined but never called
- `OPTIMIZED_*` constants exported but agent uses `DSPyInterpreter.render()` instead

### 14. Worker Memory Leak

`agent.ts:33-65` event handler only removed on SUCCESS/ERROR. Other message types cause accumulation.

### 15. Overly Complex Orchestrator Prompt

`prompts.ts:67-102` — 41-line prompt with competing directives for a 1.5B model.

**Fix:** Split into simpler SQL generator + separate validation step. Let DSPy optimize each independently.

---

## LOW-MEDIUM Issues

| Issue | Location | Note |
|-------|----------|------|
| Global mutable state | `agent.ts:80-82` | Race condition on concurrent queries |
| Excessive `any` types | `agent.ts`, `dspy-interpreter.ts` | Defeats TypeScript safety |
| No confidence scoring | `prompts.ts` | Can't distinguish high/low confidence |
| Redundant `getAllLogs()` calls | `logger.ts:162-194` | Parses localStorage 3x per export |
| Duplicate `getFailures`/`getSuccesses` | `logger.ts:89-124` | Should be single parameterized function |
| FIFO log rotation at 100 | `logger.ts:29` | Loses early data; biases training |
| Inconsistent DB worker response shape | `db.worker.ts:82-111` | Truncated vs normal responses differ |
| No worker init order guarantee | All workers | Undefined behavior on early queries |
| No optimization metadata in artifacts | `optimize_prompts.py:146` | Can't compare optimization runs |
| Hardcoded benchmark subset `[:10]` | `benchmark_optimized.py:56` | Non-representative sample, ordering bias |
| SQL injection in migration script | `data_migration.py:32` | Unquoted table name interpolation |

---

## Prioritized Action Plan

Given current focus on golden dataset validation followed by DSPy optimization:

1. **Standardize golden dataset schema** — Bring all entries to Format A. Fix owner_name/manager_name. This is the current task and highest leverage fix.
2. **Implement train/val/test split** — Before any optimization run.
3. **Fix DSPy metrics** — Structural SQL comparison, partial credit for tables, canonicalized intent matching.
4. **Normalize output schemas** — Unify DSPy signature and base prompt field names.
5. **Add JSON parse recovery** — Critical for production reliability with 1.5B model.
6. **Fix export pipeline escaping** — Before next deployment cycle.
7. **Populate `tablesUsed` in logs** — Enables data-driven table router improvement.
8. **Add prompt version tracking** — Enables flywheel attribution.
