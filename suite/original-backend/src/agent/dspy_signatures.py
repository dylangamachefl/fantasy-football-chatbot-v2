import dspy
from typing import List

class QueryEnhancerSignature(dspy.Signature):
    """
    Rewrite the user's question to be specific and narratively rich.
    Resolve pronouns using the conversation history.
    """
    history = dspy.InputField(desc="The conversation history so far")
    user_query = dspy.InputField(desc="The latest user question to rewrite")
    enhanced_query = dspy.OutputField(desc="The rewritten, self-contained question")

class TableRouterSignature(dspy.Signature):
    """
    Identify the database tables required to answer the user's question.
    Select specialty tables if the question implies them.
    Core tables (FantasyOwners, FantasySeasons, FantasyTeams, FantasyMatchups) are always included, so focus on specialty ones.
    """
    user_query = dspy.InputField(desc="The user's question")
    table_descriptions = dspy.InputField(desc="Descriptions of available tables")
    hint = dspy.InputField(desc="Hints about detected entities (e.g. owners)")
    selected_tables = dspy.OutputField(desc="List of specialty table names needed")
    reasoning = dspy.OutputField(desc="Reasoning for the selection")

class SQLGeneratorSignature(dspy.Signature):
    """
    Generate a valid SQLite query to answer the question based on the schema.
    Follow specific SQL recipes for Head-to-Head and Rankings.
    """
    question = dspy.InputField(desc="The user's specific question")
    db_schema = dspy.InputField(desc="The database schema with table and column details")
    previous_sql = dspy.InputField(desc="The previously generated SQL query that failed", optional=True)
    error_message = dspy.InputField(desc="The error message returned from the database", optional=True)
    sql_query = dspy.OutputField(desc="The executable SQLite query")
    thought = dspy.OutputField(desc="Brief logic for the query")

class ResponderSignature(dspy.Signature):
    """
    Answer the user's question based on the database results.
    The data_context includes the column headers to understand the meaning of the values.
    """
    history = dspy.InputField(desc="Conversation history including the user question")
    data_context = dspy.InputField(desc="The data returned from the database query")
    answer = dspy.OutputField(desc="The natural language response to the user")
