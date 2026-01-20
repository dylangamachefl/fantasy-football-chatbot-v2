import dspy

class IntentRouter(dspy.Signature):
    """Classify the user intent to determine the execution path."""
    question = dspy.InputField()
    intent = dspy.OutputField(desc="One of: 'sql_query' (data needed), 'conversational' (chit-chat), 'visualization' (charts/tables), 'league_rules' (settings), 'league_history' (narration)")
    priority = dspy.OutputField(desc="Numerical priority 1-5")

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
    """
    Given a user question, a database schema, and optional few-shot examples,
    generate a correct, optimized SQL query for SQLite.
    If a previous SQL attempt failed, the error message and previous SQL are provided for correction.
    """
    question = dspy.InputField()
    db_schema = dspy.InputField()
    examples = dspy.InputField(desc="Few-shot examples of question-SQL pairs")
    previous_sql = dspy.InputField(desc="Optional previous SQL attempt that failed")
    error_message = dspy.InputField(desc="Optional error message from the previous failed attempt")
    reasoning = dspy.OutputField(desc="Step-by-step logic for entity selection and calculation")
    sql_query = dspy.OutputField(desc="The generated SQL query")
