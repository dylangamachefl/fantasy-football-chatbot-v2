import streamlit as st
import pandas as pd
import json
import os
from utils import load_golden_dataset, save_golden_dataset, list_logs, load_log_file, run_script, ROOT_DIR

st.set_page_config(page_title="FF-Chatbot Sidecar", layout="wide")

st.title("🚀 FF-Chatbot: Developer Mission Control")
st.markdown("---")

# Sidebar for Navigation
module = st.sidebar.radio("Select Module", ["Golden Dataset Curator", "Evaluation & Diff Engine", "Flywheel Remote Control", "Signature Inspector"])

# 1. Golden Dataset Curator
if module == "Golden Dataset Curator":
    st.header("🏆 Golden Dataset Curator (HITL)")
    
    # --- Edit Golden Dataset ---
    st.subheader("Edit Golden Dataset")
    golden_data = load_golden_dataset()
    if golden_data:
        df = pd.DataFrame(golden_data)
        # Ensure only necessary columns are editable for simplicity
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        
        if st.button("Save Changes to shared/golden_dataset.json"):
            new_data = edited_df.to_dict('records')
            save_golden_dataset(new_data)
            st.success("Successfully saved changes!")
    else:
        st.warning("No golden dataset found.")

    st.markdown("---")
    
    # --- Log Ingester ---
    st.subheader("📥 Silver Log Ingester")
    logs = list_logs()
    if logs:
        selected_log = st.selectbox("Select Log File to Review", logs)
        log_content = load_log_file(selected_log)
        
        if log_content:
            # Handle different log formats (all-feedback vs failures-for-teacher)
            items_to_review = []
            if isinstance(log_content, list):
                items_to_review = log_content
            elif 'failures' in log_content:
                items_to_review = log_content['failures']
            elif 'successes' in log_content:
                items_to_review = log_content['successes']
                
            if items_to_review:
                review_df = pd.DataFrame(items_to_review)
                st.write(f"Found {len(items_to_review)} items in this log.")
                
                # Show selection for promotion
                selected_indices = st.multiselect("Select queries to promote to GOLD", review_df.index, format_func=lambda x: f"[{x}] {review_df.iloc[x]['question'][:100]}...")
                
                if st.button("Promote Selected to Gold"):
                    promoted_entries = review_df.iloc[selected_indices].to_dict('records')
                    # Basic cleaning to match golden schema
                    for entry in promoted_entries:
                        # Ensure fields exist or default
                        entry.setdefault('reasoning', "Promoted from logs.")
                        entry.setdefault('intent', "sql_query")
                        entry.setdefault('category', "unknown")
                        entry.setdefault('selected_tables', [])
                        entry.setdefault('sql', entry.get('sql', "NONE"))
                        entry.setdefault('answer', entry.get('answer', "Pending analysis..."))
                    
                    golden_data.extend(promoted_entries)
                    save_golden_dataset(golden_data)
                    st.success(f"Promoted {len(promoted_entries)} entries to golden dataset!")
            else:
                st.info("No entries found in this log.")
    else:
        st.info("No log files found in logs/ directory.")

# 2. Evaluation & Diff Engine
elif module == "Evaluation & Diff Engine":
    st.header("📊 Evaluation & Diff Engine")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Intent Accuracy", "92%", "+3%")
    col2.metric("Table Selection", "88%", "-2%")
    col3.metric("SQL Accuracy", "85%", "+5%")
    
    st.markdown("---")
    st.subheader("Optimization Diff")
    
    from utils import load_compiled_artifact
    compiled_data = load_compiled_artifact()
    if compiled_data:
        st.write("Current Compiled Instructions:")
        st.json(compiled_data)
    else:
        st.warning("Compiled agent artifact not found. Run optimization first.")

# 3. Flywheel Remote Control
elif module == "Flywheel Remote Control":
    st.header("⚙️ Flywheel Remote Control")
    st.markdown("Trigger backend processing scripts directly from here.")
    
    scripts = {
        "Extract Failures": "suite/evaluation/extract_failures.py",
        "Generate Golden Entries (Teacher)": "suite/evaluation/generate_golden_entries.py",
        "Run DSPy Optimization": "suite/evaluation/optimize_prompts.py",
        "Export Prompts to App": "suite/evaluation/export_prompts.py"
    }
    
    col_a, col_b = st.columns(2)
    
    for i, (name, path) in enumerate(scripts.items()):
        target_col = col_a if i % 2 == 0 else col_b
        if target_col.button(f"▶️ {name}"):
            st.info(f"Running {name}...")
            output_container = st.empty()
            full_output = ""
            
            absolute_path = os.path.join(ROOT_DIR, path)
            for line in run_script(absolute_path):
                full_output += line
                output_container.code(full_output)
            
            st.success(f"Finished: {name}")

# 4. Signature Inspector
elif module == "Signature Inspector":
    st.header("🔍 DSPy Signature Inspector")
    st.markdown("Visual bridge between Signature Blueprints and Compiled Results.")

    import sys
    eval_path = os.path.join(ROOT_DIR, "suite", "evaluation")
    if eval_path not in sys.path:
        sys.path.append(eval_path)
    
    try:
        from dspy_signatures import IntentRouter, TableRouterSignature, SQLGeneratorSignature, SQLOrchestrator
        from utils import get_signature_info, load_compiled_artifact
        
        compiled_data = load_compiled_artifact()
        
        tab1, tab2, tab3, tab4 = st.tabs(["Intent Router", "Table Router", "SQL Generator", "SQL Orchestrator"])
        
        sig_map = {
            "Intent Router": (IntentRouter, "intent_router"),
            "Table Router": (TableRouterSignature, "table_router"),
            "SQL Generator": (SQLGeneratorSignature, "sql_generator"),
            "SQL Orchestrator": (SQLOrchestrator, "sql_orchestrator") # Optional mapping if exists in compiled
        }
        
        for tab, (tab_name, (sig_class, json_key)) in zip([tab1, tab2, tab3, tab4], sig_map.items()):
            with tab:
                info = get_signature_info(sig_class)
                
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.subheader("📋 Blueprint (Contract)")
                    st.info(f"**Instruction:** {info['doc']}")
                    
                    st.write("**Input Fields:**")
                    for f in info['inputs']:
                        st.markdown(f"- `{f['name']}`: {f['description']}")
                    
                    st.write("**Output Fields:**")
                    for f in info['outputs']:
                        st.markdown(f"- `{f['name']}`: {f['description']}")
                
                with col_right:
                    st.subheader("✨ Result (Optimized)")
                    if compiled_data and json_key in compiled_data:
                        module_data = compiled_data[json_key]
                        
                        # Extract instructions
                        # Note: Compiled structure can vary, check both 'instructions' and 'signature.instructions'
                        instructions = module_data.get('instructions')
                        if not instructions and 'signature' in module_data:
                            instructions = module_data['signature'].get('instructions')
                        if not instructions and 'predictor' in module_data:
                            instructions = module_data['predictor'].get('signature', {}).get('instructions')

                        if instructions:
                            st.code(instructions, language="text")
                        else:
                            st.warning("No optimized instructions found in artifact.")
                        
                        # Demo Inspector
                        st.markdown("---")
                        st.subheader("💡 Few-Shot Demos")
                        demos = module_data.get('demos', [])
                        if not demos and 'predictor' in module_data:
                            demos = module_data['predictor'].get('demos', [])
                        
                        if demos:
                            st.json(demos)
                        else:
                            st.info("No few-shot demonstrations found for this module.")
                    else:
                        st.warning(f"No compiled data found for '{json_key}'. Run optimization first.")
    except ImportError as e:
        st.error(f"Error importing signatures: {e}")
    except Exception as e:
        st.error(f"An error occurred: {e}")

st.sidebar.markdown("---")
st.sidebar.info("Sidecar Dashboard v1.1")
