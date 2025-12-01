import dspy
from .dspy_signatures import QueryEnhancerSignature, TableRouterSignature, SQLGeneratorSignature, ResponderSignature
from .dspy_config import get_optimized_program

class QueryEnhancerModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.ChainOfThought(QueryEnhancerSignature)

    def forward(self, history, user_query):
        return self.prog(history=history, user_query=user_query)

class TableRouterModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.ChainOfThought(TableRouterSignature)

    def forward(self, user_query, table_descriptions, hint):
        return self.prog(user_query=user_query, table_descriptions=table_descriptions, hint=hint)

class SQLGeneratorModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.ChainOfThought(SQLGeneratorSignature)

    def forward(self, question, db_schema):
        return self.prog(question=question, db_schema=db_schema)

class ResponderModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.ChainOfThought(ResponderSignature)

    def forward(self, history, data_context):
        return self.prog(history=history, data_context=data_context)

# Singleton instances or factory functions can be used
def get_query_enhancer():
    mod = QueryEnhancerModule()
    return get_optimized_program("query_enhancer", mod)

def get_table_router():
    mod = TableRouterModule()
    return get_optimized_program("table_router", mod)

def get_sql_generator():
    mod = SQLGeneratorModule()
    return get_optimized_program("sql_generator", mod)

def get_responder():
    mod = ResponderModule()
    return get_optimized_program("responder", mod)
