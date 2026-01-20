// Ported from backend/src/agent/dspy_signatures.py

export const PROMPTS = {
  // Intent Router
  intentRouter: (question: string) => `
Classify the user intent to determine the execution path.
Intents: 
- 'sql_query': Complex data needed from database.
- 'conversational': Simple chit-chat or greeting.
- 'visualization': Request for charts, tables, or structured lists.
- 'league_rules': Questions about bylaws, scoring, or settings.
- 'league_history': Narrative questions about the league's past or lore.

Question: ${question}

Respond in JSON format: { "intent": "sql_query" | "conversational" | "visualization" | "league_rules" | "league_history", "priority": 1-5 }
`,

  // SQL Orchestrator (ReAct)
  orchestrator: (question: string, observations: string, sqlHints: string, managerName: string, workingMemory: any, schema: string) => `
Reason through a fantasy football question and decide which SQL actions to take.
You can think in steps, deciding which tables to query sequentially if needed.

USER IDENTITY:
- The active manager is: ${managerName}
- When the user says "I", "me", or "my", filter by owner_name = '${managerName}'.
- Working Memory: ${JSON.stringify(workingMemory)}

SCHEMA RULES:
1. STRICT COLUMN NAMING: Do not pluralize or singularize columns. If the schema says "championships_won", do not use "championship_won". 
2. TABLE TYPES: 'Fact_Manager_Career_Leaderboard' is an AGGREGATE table. It does NOT have a 'season_id'. Use 'Fact_Team_Season_Standings' for season-specific results.

[RICH PROJECTION RULE]:
When writing SQL actions, ALWAYS SELECT SUPPORTING COLUMNS.
If filtering by a column (e.g., championships_won > 0), you MUST include that column in the SELECT clause.
Example: If asked for "who has most points", SELECT owner_name, total_points (don't just select the name).
This ensures the final analyzer can see the numbers!

ERROR REFLECTION:
If an 'Observation' contains a SQL error, you MUST compare your failed query against the provided schema and fix the specific column or table name that caused the failure.

AVAILABLE SCHEMA:
${schema}

CONTEXT:
Observations from previous steps:
${observations}

SQL Retrieval Hints:
${sqlHints}

Question: ${question}

Respond in JSON format: { "thought": "...", "action": "SQL query here or 'Final Answer'" }
`,

  // Query Enhancer
  queryEnhancer: (history: string, userQuery: string, validOwners: string[], managerName: string, entityMap: string) => `
You are a Query Enhancer for a Fantasy Football database. 
Rewrite the user's question to be a precise, de-aliased technical query for a database.
Resolve pronouns and ambiguous references using the conversation history.

DB_ENTITY_MAP:
${entityMap}

DIRECTIVE:
Before rewriting, check the DB_ENTITY_MAP. If a user asks for 'championships', do not rewrite the subject to 'players', as championships are a Manager-level metric.

IMPORTANT: The user is ${managerName}. 
If they say "me", "my team", "my record", or "how did I do", map this specifically to "${managerName}".

VALID OWNER NAMES:
${validOwners.join(', ')}

History:
${history}

User Query:
${userQuery}

Respond with ONLY the rewritten query. Focus on clarity and specificity, not narrative flair.
`,

  // Table Router
  tableRouter: (userQuery: string, tableDescriptions: string) => `
Identify which database tables are absolutely necessary to answer the user's question.

Table Descriptions:
${tableDescriptions}

User Query:
${userQuery}

Respond in JSON format: { "selected_tables": ["Table1", "Table2"], "is_sql_query": true/false, "reasoning": "..." }
`,

  // SQL Generator
  sqlGenerator: (question: string, schema: string, managerName: string, workingMemory: any, previousSql: string = "", errorMessage: string = "", examples: string = "") => `
Generate a valid SQLite query to answer the question based on the schema.
Only use the tables and columns provided in the schema.

[RICH PROJECTION RULE]:
Always include the value column you are filtering or ordering by in the SELECT clause.
If filtering by a column (e.g., championships_won > 0), you MUST include that column in the SELECT clause.
If asked for "highest points", include the points column. If asked for "most wins", include the wins column.
This provides necessary context for the final analyst.

USER CONTEXT:
- The active manager is: ${managerName}
- Working Memory: ${JSON.stringify(workingMemory)}
- IMPORTANT: When the question references "my", "me", or "I", use "${managerName}" in the SQL query.
- NEVER use placeholder values like 'Your Manager Name', '[Manager Name]', or '{manager_name}' in the SQL.
- Always use the actual value: '${managerName}'

Schema:
${schema}

${examples ? `Examples (Use these for style and table choice reference):\n${examples}\n` : ''}

${previousSql ? `Previous Failed SQL: ${previousSql}\nError Message: ${errorMessage}\nFix the error.` : ''}

Question:
${question}

VALIDATION STEP:
Before writing the SQL, think through the entity requirements. 
If the question asks for 'players with championships', note the entity mismatch in your reasoning (Championships belong to Managers) and target the correct table.

Respond in JSON format: { "reasoning": "...", "sql": "..." }
`,

  // Responder
  responder: (history: string, dataContext: string) => `
You are an Expert Fantasy Football Analyst.

CORE RULES:
1. RESULT INTERPRETATION: Use the [HISTORY] to understand the "Intent" behind the [DATA]. If the user asks for "who...", and the data returns a single name, conclude that person is the answer based on the context of their question.
2. DATA SUPREMACY: Use the "Live Database Feed" ([DATA]) as your source of truth for stats. Do not invent numbers that aren't there.
3. NO HALLUCINATION: If the [DATA] is empty, state that the records do not contain the answer.
4. TONE: Professional, analytical, and concise.

[DATA]
${dataContext ? dataContext : "No relevant data found in the database."}

${history ? `[HISTORY]\n${history}\n` : ''}

Analysis (Connect the User's question to the Data result):
`,

  // Format Selector
  formatSelector: (question: string, data: string) => `
Analyze the question and the resulting data. Decide the best format for the user:
- "sentence": Use for single facts or very short answers.
- "table": Use for structured lists or comparisons.
- "list": Use for a simple list of names or items.
- "no_data": Use if the data is empty or irrelevant.
- "breaking_news": Use for major achievements, massive blowouts, or significant statistical milestones.

Question: ${question}
Data: ${data}

Respond with ONLY the format type.
`,

  // Phase 7: Slot Filler
  slotFiller: (query: string, currentMemory: string) => `
Extract specific entities from the user query to update the "Working Memory".
Current Memory: ${currentMemory}
Query: ${query}

Identifiable Entity Categories:
- Manager (e.g., Dylan, Chris)
- Season (e.g., 2022, 2023)
- Player (e.g., Christian McCaffrey)
- Week (e.g., Week 5)

ENTITY TYPE LOGIC:
- 'Manager': Use if the user asks about records, career stats, championships, final standings, or team-level ownership.
- 'Player': Use if the user asks about individual player points, yards, TDs, weekly performance, or specific NFL player names.
- 'League': Use if the user asks about overall league rules, settings, or broad history not tied to one manager/player.
- 'None': Default if no entity type is clearly identified.

Respond in JSON format: { "Manager": "...", "Season": "...", "Player": "...", "Week": "...", "EntityType": "Manager" | "Player" | "League" | "None" }
For any category not mentioned or implied, use the value from Current Memory.
`
};
