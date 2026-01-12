import httpx, json, sys

def call_api(query, thread_id=None):
    """Call the non‑streaming /chat endpoint.
    Returns (answer, thread_id)."""
    url = "http://localhost:8000/chat"
    payload = {"query": query, "thread_id": thread_id}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get('answer', ''), data.get('thread_id')
    except Exception as e:
        print('API request failed:', e, file=sys.stderr)
        return '', None

if __name__ == '__main__':
    # First request – simple question
    ans1, thread = call_api("Who won the 2020 championship?")
    print('First response:', ans1)
    print('Thread ID:', thread)
    # Second request – should reuse thread and return answer (SQL data shown in debug if enabled)
    ans2, _ = call_api("Show me Dylan's all-time record", thread)
    print('Second response:', ans2)
