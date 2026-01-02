// Ported from backend/src/agent/dspy_signatures.py

export const PROMPTS = {
  // Query Enhancer
  queryEnhancer: (history: string, userQuery: string) => `
You are a Query Enhancer. Rewrite the user's question to be specific and narratively rich. Resolve pronouns using the conversation history.

History:
${history}

User Query:
${userQuery}

Respond with ONLY the rewritten query.
`,

  // Table Router
  tableRouter: (userQuery: string, tableDescriptions: string) => `
Identify the database tables required to answer the user's question.
Select specialty tables if the question implies them.
Core tables (FantasyOwners_LLM, FantasySeasons_LLM, FantasyTeams_LLM, FantasyMatchups_LLM) are usually relevant, but focus on detecting specific needs.

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
`
};
