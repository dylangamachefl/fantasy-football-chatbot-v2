import json
import os
from langfuse import Langfuse
from eval_config import (
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST
)

# Initialize Langfuse
langfuse = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    host=LANGFUSE_HOST
)

def extract_failures():
    """
    Fetch traces from Langfuse that have a user-feedback score < 1.
    Extract the original user query and save as a list for the Teacher.
    """
    print(f"Connecting to Langfuse at {LANGFUSE_HOST}...")
    
    # 1. Fetch scores that are less than 1 (indicates downvote)
    # Langfuse SDK 3.x uses langfuse.api.score_v_2.get() for list retrieval
    try:
        scores_response = langfuse.api.score_v_2.get(name="user-feedback")
    except Exception as e:
        print(f"Error fetching scores: {e}")
        return []
    
    failure_trace_ids = []
    for score in scores_response.data:
        # User feedback value: 1 for ThumbsUp, -1 for ThumbsDown
        if score.value < 1:
            failure_trace_ids.append(score.trace_id)
            
    print(f"Found {len(failure_trace_ids)} traces with negative user feedback.")
    
    queries = []
    processed_traces = set()

    for trace_id in failure_trace_ids:
        if trace_id in processed_traces:
            continue
            
        try:
            trace = langfuse.get_trace(trace_id)
            # Input to 'agent-process-query' is saved in trace.input
            # Based on agent.ts: trace = langfuse.trace({ name: 'agent-process-query', input: { userQuery, ... } })
            user_query = trace.input.get("userQuery")
            if user_query:
                queries.append(user_query)
                processed_traces.add(trace_id)
        except Exception as e:
            print(f"Error fetching trace {trace_id}: {e}")

    # Remove duplicates
    unique_queries = list(set(queries))
    
    print(f"Extracted {len(unique_queries)} unique failure queries.")
    
    # Save to a temporary file for the Teacher
    output_path = "suite/evaluation/extracted_failures.json"
    with open(output_path, 'w') as f:
        json.dump(unique_queries, f, indent=2)
        
    print(f"Failures saved to {output_path}")
    return unique_queries

if __name__ == "__main__":
    extract_failures()
