# Manual Verification Steps

## Test 1: Pre-computed Embeddings (Zero-Latency Boot)

1. Open the browser console (F12)
2. Refresh the page at http://localhost:5173/
3. Select a manager (e.g., Dylan) to complete onboarding
4. Watch the console logs during initialization
5. **Expected Result**: You should see:
   - `[RAG Worker] SQL bank already contains embeddings. Skipping calculation.`
   - `[RAG Worker] LORE bank already contains embeddings. Skipping calculation.`
   - Initialization should complete in milliseconds, not seconds

## Test 2: SQL Row Limit (1,000 rows)

1. After the system is ready, send this query in the chat:
   ```
   Show me all records from Fact_Player_Performance_Weekly
   ```
2. Watch the console logs
3. **Expected Results**:
   - Console should show: `[DB Worker] SQL query exceeded limit of 1000 rows. Returning partial results.`
   - UI should display a thought: `Caution: Query exceeded maximum limit of 1000 rows. Results are truncated.`
   - The application should remain stable (no crash)

## Test 3: Batched RAG Retrieval

1. Open the Network tab in browser console
2. Filter by "WS" (WebSocket) or look for worker messages
3. Send a normal analytical query like:
   ```
   Who is the best running back in 2023?
   ```
4. **Expected Result**:
   - Console should show: `[RAG Worker] Starting batch retrieval for 2 requests`
   - Only ONE message of type `RETRIEVE_BATCH` should be sent to the RAG worker
   - (Previously, there would be TWO separate `RETRIEVE` messages)

## Test 4: Memory Serialization Optimization

This is harder to verify visually, but you can:
1. Open the Sources tab in DevTools
2. Set a breakpoint in `agent.ts` at the `processQuery` method
3. Send a query
4. Verify that `memoryStr` is created once at the top
5. Step through and confirm it's reused in both `slotFiller` and `queryEnhancer` prompts
