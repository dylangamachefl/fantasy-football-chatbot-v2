import dspy

class IntentRouter(dspy.Signature):
    """Classify the user's intent to route to the correct specialist."""
    
    question = dspy.InputField(desc="The user's fantasy football question")
    intent = dspy.OutputField(desc="One of: [sql_query, conversational, league_rules, league_history]")
    reasoning = dspy.OutputField(desc="Brief explanation for the chosen intent")

class SQLOrchestrator(dspy.Signature):
    """Reason through a fantasy football question and decide which SQL actions to take."""
    question = dspy.InputField()
    context = dspy.InputField(desc="Working memory and previous SQL results")
    thought = dspy.OutputField(desc="Internal reasoning about what data is missing")
    action = dspy.OutputField(desc="SQL query to execute or 'Final Answer' to finish")


class TableRouterSignature(dspy.Signature):
    """
    Given a user question and descriptions of available database tables,
    identify which tables are necessary to answer the question.
    Also indicate if the question requires a SQL query.
    """
    question = dspy.InputField()
    table_descriptions = dspy.InputField()
    selected_tables = dspy.OutputField(desc="List of table names required for the query")
    is_sql_query = dspy.OutputField(desc="Boolean indicating if a SQL query is needed")

class SQLGeneratorSignature(dspy.Signature):
    """Generate a valid SQLite query to answer the question.
    
    Check the schema carefully. Ensure all table and column names are correct.
    Before writing the SQL, think through the entity requirements.
    """
    
    question: str = dspy.InputField(desc="User's fantasy football question")
    db_schema: str = dspy.InputField(desc="Available database schema with tables and columns")
    examples: str = dspy.InputField(desc="Example queries for context", default="")
    previous_sql: str = dspy.InputField(desc="Previous SQL attempt if any", default="")
    error_message: str = dspy.InputField(desc="Error from previous SQL if any", default="")
    
    reasoning: str = dspy.OutputField(desc="Reasoning about what data is needed and how to get it")
    sql_query: str = dspy.OutputField(desc="Valid SQLite SELECT query")


class SQLValidatorSignature(dspy.Signature):
    """Validate and optionally correct a generated SQL query.
    
    Check that all table/column names exist in the schema, joins are reasonable,
    and the query addresses the question intent.
    """
    
    question: str = dspy.InputField(desc="Original user question")
    sql_query: str = dspy.InputField(desc="SQL query to validate")
    db_schema: str = dspy.InputField(desc="Available database schema")
    
    is_valid: bool = dspy.OutputField(desc="Whether the SQL is valid")
    issues: str = dspy.OutputField(desc="List of issues found, empty if valid")
    corrected_sql_query: str = dspy.OutputField(desc="Corrected SQL query if issues found, else original query")
