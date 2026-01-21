# 🛠 The Developer Suite

This directory contains the "Mission Control" tools for the Fantasy Football Chatbot. It is designed to be run locally by developers to optimize, evaluate, and manage the system's performance.

## 📂 Directories

- **`dashboard/`**: A React-based sidecar UI to visualize evaluations, curate the golden dataset, and manage prompts.
- **`evaluation/`**: Python scripts and DSPy signatures for offline prompt optimization and accuracy benchmarking.
- **`data-ops/`**: Utilities for extracting failure logs from the app and generating "Silver" data for labeling.
- **`observability/`**: (Legacy) Local Langfuse Docker stack. Traces are now predominantly handled via local logging + the dashboard.

## 🔄 The Optimization Flywheel

The chatbot uses a "Teacher-Student" architecture to continuously improve.

1. **Extraction**: failed queries (thumbs down) are exported from the `chat-app`'s local storage.
2. **Teacher Review**: `suite/evaluation/generate_golden_entries.py` uses a high-capacity "Teacher" model (e.g., Qwen 72B via Ollama) to label failures with correct SQL and reasoning.
3. **DSPy Compilation**: `suite/evaluation/optimize_prompts.py` uses the new golden examples to optimize the "Student" prompts (WebLLM/Qwen 7B).
4. **Validation**: Run `suite/evaluation/judge_results.py` to compare the optimized Student vs. the Teacher.

## 🚀 Running the Dashboard

```bash
cd suite/dashboard
npm install
npm run dev
```

Open [http://localhost:5174](http://localhost:5174) to access Mission Control.

## 🤖 Running Evaluations

Ensure you have the Python dependencies installed:
```bash
cd suite/evaluation
pip install -r requirements.txt
```

To run a full optimization run:
```bash
python optimize_prompts.py
```
