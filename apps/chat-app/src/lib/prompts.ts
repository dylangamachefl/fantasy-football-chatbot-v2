// Ported from backend/src/agent/dspy_signatures.py

export const PROMPTS = {
  // Query Enhancer
  queryEnhancer: (history: string, userQuery: string, validOwners: string[]) => `
You are a Query Enhancer for a Fantasy Football database. 
Rewrite the user's question to be specific and narratively rich. 
Resolve pronouns using the conversation history.

VALID OWNER NAMES (Only use these names for league members):
${validOwners.join(', ')}

History:
${history}

User Query:
${userQuery}

Respond with ONLY the rewritten query. If the user mentions a name close to one of the valid owners, use the canonical name from the list.
`,

  // Table Router
  tableRouter: (userQuery: string, tableDescriptions: string) => `
Identify which database tables are absolutely necessary to answer the user's question.
If the question is about league history or "lore" that doesn't sound like a database query, you can skip SQL-specific tables.

Table Descriptions:
${tableDescriptions}

User Query:
${userQuery}

Respond in JSON format: { "selected_tables": ["Table1", "Table2"], "is_sql_query": true/false, "reasoning": "..." }
`,

  // SQL Generator
  sqlGenerator: (question: string, schema: string, previousSql: string = "", errorMessage: string = "", examples: string = "") => `
Generate a valid SQLite query to answer the question based on the schema.
Only use the tables and columns provided in the schema.

Schema:
${schema}

${examples ? `Examples (Use these for style and table choice reference):\n${examples}\n` : ''}

${previousSql ? `Previous Failed SQL: ${previousSql}\nError Message: ${errorMessage}\nFix the error.` : ''}

Question:
${question}

Respond with ONLY the SQL query.
`,

  // Responder
  responder: (history: string, dataContext: string, loreContext: string = "") => `
Answer the user's question based on the provided information.

${loreContext ? `League Lore Context:\n${loreContext}\n` : ''}
${dataContext ? `Database Results:\n${dataContext}\n` : ''}

History:
${history}

Answer naturally as a knowledgeable Fantasy Football Assistant. 
If you have data results, summarize them. 
If you have lore facts, weaving them into the narrative is encouraged.
If there is no information at all, explain that you don't have the specific answer in your records.

Answer:
`,

  // Format Selector
  formatSelector: (question: string, data: string) => `
Analyze the question and the resulting data. Decide the best format for the user:
- "sentence": Use for single facts or very short answers.
- "table": Use for structured lists or comparisons.
- "list": Use for a simple list of names or items.
- "no_data": Use if the data is empty or irrelevant.

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

If the query explicitly mentions a new entity, update the slot.
If the query implies an entity (e.g., "And what about him?"), do not change the slot unless certain.

Respond in JSON format: { "Manager": "...", "Season": "...", "Player": "...", "Week": "..." }
For any category not mentioned or implied, use the value from Current Memory.
`
};
