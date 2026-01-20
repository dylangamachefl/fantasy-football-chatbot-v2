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
  orchestrator: (question: string, observations: string, sqlHints: string) => `
Reason through a fantasy football question and decide which SQL actions to take.
You can think in steps, deciding which tables to query sequentially if needed.

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
1. DATA SUPREMACY: Use the "Live Database Feed" below as your SOLE source of truth for stats, scores, and records.
2. NO HALLUCINATION: If the [DATA] section is empty or does not contain the answer, explicitly state that the information is not in the league records. Do not invent history.
3. TONE: Professional, analytical, and concise.

[DATA]
${dataContext ? dataContext : "No relevant data found in the database."}

${history ? `[HISTORY]\n${history}\n` : ''}

Provide your analysis based ONLY on the provided data:
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
