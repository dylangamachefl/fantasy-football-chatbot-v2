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
Identify the database tables required to answer the user's question.
Select specialty tables if the question implies them.
Core tables (FantasyOwners_LLM, FantasySeasons_LLM, FantasyTeams_LLM, FantasyMatchups_LLM) are always included, so focus on specialty ones.

Table Descriptions:
${tableDescriptions}

User Query:
${userQuery}

Respond in JSON format: { "selected_tables": ["Table1", "Table2"], "reasoning": "..." }
`,

  // SQL Generator
  sqlGenerator: (question: string, schema: string, previousSql: string = "", errorMessage: string = "", examples: string = "") => `
Generate a valid SQLite query to answer the question based on the schema.
Follow specific SQL recipes for Head-to-Head and Rankings.

Schema:
${schema}

${examples ? `Examples:\n${examples}\n` : ''}

${previousSql ? `Previous Failed SQL: ${previousSql}\nError Message: ${errorMessage}\nFix the error.` : ''}

Question:
${question}

Respond with ONLY the SQL query. Do not include markdown code blocks like \`\`\`sql.
`,

  // Responder
  responder: (history: string, dataContext: string) => `
Answer the user's question based on the database results.
The data includes column headers to understand the values.

History:
${history}

Data:
${dataContext}

Answer:
`,

  // Format Selector
  formatSelector: (question: string, data: string) => `
Analyze the question and the resulting data. Decide the best format for the user:
- "sentence": Use for single facts or very short answers (e.g. "Who won?" -> "Zach won.")
- "table": Use for structured lists or comparisons (e.g. "Top 5 points")
- "list": Use for a simple list of names or items.
- "no_data": Use if the data is empty or irrelevant.

Question: ${question}
Data: ${data}

Respond with ONLY the format type.
`
};
