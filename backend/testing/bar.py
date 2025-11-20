import pandas as pd
import os

# --- File 1: Simple 1-Turn Stress-Test Questions ---

simple_questions = [
    # --- Basic Joins & Lookups ---
    {
        "question_id": "simple_001",
        "question": "Who won the championship in 2022?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_002",
        "question": "What was Jack's regular season record in 2023?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_003",
        "question": "How many total points did Chris score during the 2021 regular season?",
        "ground_truth_answer": "",
    },
    # --- Aggregations & Joins ---
    {
        "question_id": "simple_004",
        "question": "Who has the most championships in league history?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_005",
        "question": "What is Zach's all-time regular season record (wins-losses-ties)?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_006",
        "question": "Who has the most runner-up finishes without ever winning a championship?",
        "ground_truth_answer": "",
    },
    # --- Complex Aggregations (Hard) ---
    {
        "question_id": "simple_007",
        "question": "What is Dylan's all-time head-to-head record against Dan in the regular season?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_008",
        "question": "What was the highest single-week score in any 2023 regular season matchup?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_009",
        "question": "What is Sean's all-time record in playoff games?",
        "ground_truth_answer": "",
    },
    {
        "question_id": "simple_010",
        "question": "List all league members who have a career regular season winning percentage over .500.",
        "ground_truth_answer": "",
    },
]

# Create DataFrame for simple questions
df_simple = pd.DataFrame(simple_questions)

# Ensure data directory exists
data_dir = "data"
os.makedirs(data_dir, exist_ok=True)

# Save simple questions CSV
output_path_simple = os.path.join(data_dir, "test_set_simple.csv")
df_simple.to_csv(output_path_simple, index=False, encoding="utf-8")
print(f"Successfully created {output_path_simple}")


# --- File 2: Multi-Step Conversational Stress-Test Questions ---

conversation_data = [
    # --- Convo 1: Champion Deep Dive (Jack) ---
    {
        "conversation_id": "stress_convo_01",
        "turn_id": 1,
        "question": "Did Jack win any championships?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_01",
        "turn_id": 2,
        "question": "What year was his most recent one?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_01",
        "turn_id": 3,
        "question": "Who did he play in that championship game and what was the score?",
        "ground_truth_answer": "",
    },
    # --- Convo 2: H2H Rivalry (Jake vs. Josh) ---
    {
        "conversation_id": "stress_convo_02",
        "turn_id": 1,
        "question": "What is Jake's all-time regular season record against Josh?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_02",
        "turn_id": 2,
        "question": "How many times did they meet in the playoffs?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_02",
        "turn_id": 3,
        "question": "Who won their most recent matchup, regular season or playoffs?",
        "ground_truth_answer": "",
    },
    # --- Convo 3: User-Specific Stats (Mark) ---
    {
        "conversation_id": "stress_convo_03",
        "turn_id": 1,
        "question": "What's my (Mark's) best regular season record?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_03",
        "turn_id": 2,
        "question": "What year was that?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_03",
        "turn_id": 3,
        "question": "Did I make the playoffs that year? If so, how far did I get?",
        "ground_truth_answer": "",
    },
    # --- Convo 4: League Records (High/Low) ---
    {
        "conversation_id": "stress_convo_04",
        "turn_id": 1,
        "question": "What's the most points ever scored in a single regular season by one team?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_04",
        "turn_id": 2,
        "question": "Who was it and what year?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_04",
        "turn_id": 3,
        "question": "What was their final record that season? Did they win the 'ship?",
        "ground_truth_answer": "",
    },
    # --- Convo 5: Comparison (Nick vs. Will) ---
    {
        "conversation_id": "stress_convo_05",
        "turn_id": 1,
        "question": "Compare the all-time playoff wins for Nick and Will.",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_05",
        "turn_id": 2,
        "question": "Who has more championships between the two?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_05",
        "turn_id": 3,
        "question": "What about total regular season points scored all-time?",
        "ground_truth_answer": "",
    },
    # --- Convo 6: Specific Season Deep Dive (2021) ---
    {
        "conversation_id": "stress_convo_06",
        "turn_id": 1,
        "question": "Who was the runner-up in 2021?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_06",
        "turn_id": 2,
        "question": "What was his team name that year?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_06",
        "turn_id": 3,
        "question": "What was his regular season record?",
        "ground_truth_answer": "",
    },
    # --- Convo 7: Pronoun/Context Stress Test (Lac & Fitz) ---
    {
        "conversation_id": "stress_convo_07",
        "turn_id": 1,
        "question": "How many championships does Lac have?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_07",
        "turn_id": 2,
        "question": "What about Fitz?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_07",
        "turn_id": 3,
        "question": "Compare their all-time head-to-head record.",
        "ground_truth_answer": "",
    },
    # --- Convo 8: 'Never Won' Logic ---
    {
        "conversation_id": "stress_convo_08",
        "turn_id": 1,
        "question": "Show me all the league members (Jack, Josh, Jake, Mark, Sean, Nick, Will, Zach, Lac, Chris, Dylan, Dan, and Fitz) who have never won a championship.",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_08",
        "turn_id": 2,
        "question": "Of that group, who has the most playoff appearances?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_08",
        "turn_id": 3,
        "question": "What's the best-ever finish for that person?",
        "ground_truth_answer": "",
    },
    # --- Convo 9: Team Name History (Sean) ---
    {
        "conversation_id": "stress_convo_09",
        "turn_id": 1,
        "question": "What was Sean's team name in 2020?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_09",
        "turn_id": 2,
        "question": "What about in 2021?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_09",
        "turn_id": 3,
        "question": "Has he ever used the same name twice?",
        "ground_truth_answer": "",
    },
    # --- Convo 10: Aggregate Comparison (Hard) ---
    {
        "conversation_id": "stress_convo_10",
        "turn_id": 1,
        "question": "Who had more regular season wins in 2023: Dylan or Chris?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_10",
        "turn_id": 2,
        "question": "What about total points scored?",
        "ground_truth_answer": "",
    },
    {
        "conversation_id": "stress_convo_10",
        "turn_id": 3,
        "question": "Did either of them make the playoffs that year?",
        "ground_truth_answer": "",
    },
]

# Create DataFrame for conversations
df_conversations = pd.DataFrame(conversation_data)

# Save conversations CSV
output_path_conversations = os.path.join(data_dir, "test_set_conversations_stress.csv")
df_conversations.to_csv(output_path_conversations, index=False, encoding="utf-8")
print(f"Successfully created {output_path_conversations}")
