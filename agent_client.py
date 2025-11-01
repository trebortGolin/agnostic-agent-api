# --- AGENT CLIENT (AC) v3.0 (Task Signing) ---
# Implements Athena's Briefing Task 2: Cryptographic task signing.
# This client handles the core conversation logic (NLU, NLG, Memory)
# and now cryptographically signs all outgoing tasks.

import google.generativeai as genai
import json
import os
import re
import base64

# --- NEW DEPENDENCIES (from requirements.txt) ---
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.exceptions import InvalidSignature

# --- 1. CONFIGURATION ---
try:
    # LLM API Key
    GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GOOGLE_API_KEY:
        raise ValueError("The GEMINI_API_KEY environment variable is not set.")
    genai.configure(api_key=GOOGLE_API_KEY)

    # --- NEW: AGENT'S PRIVATE KEY (for signing) ---
    # Load the Agent's Private Key from environment variables (Task 2)
    AGENT_PRIVATE_KEY_PEM = os.environ.get("AGENT_PRIVATE_KEY")
    if not AGENT_PRIVATE_KEY_PEM:
        raise ValueError("The AGENT_PRIVATE_KEY environment variable is not set.")

    # Load the PEM-formatted private key
    # Ed25519 keys do not require a password
    AGENT_PRIVATE_KEY = load_pem_private_key(
        AGENT_PRIVATE_KEY_PEM.encode('utf-8'),
        password=None
    )

    # --- END NEW CONFIG ---

except Exception as e:
    print(f"--- CONFIGURATION ERROR ---")
    print(f"Error: {e}")
    print("Please set your GEMINI_API_KEY and AGENT_PRIVATE_KEY before running the script.")
    print("Run `openssl genpkey -algorithm Ed25519 -out agent_private_key.pem` to generate a key.")
    exit()

# --- v3.0: TWO BRAINS (NLU and NLG) ---

# --- NLU BRAIN (Phase 0) ---
# This system prompt remains unchanged from v2.1
NLU_SYSTEM_PROMPT = """
You are an expert NLU (Natural Language Understanding) agent for a travel agency.
Your sole task is to update a JSON object based on the user's request.
Respond with NOTHING but the final JSON.

You will receive:
1.  "Previous JSON State": The state of the conversation (can be empty {}).
2.  "Current User Request": What the user just said.

Your rules:
- Identify the user's intent: 'SEARCH_FLIGHT', 'SEARCH_HOTEL', 'BOOK_ITEM', or 'CLARIFICATION'.
- If the request is a *new* search (e.g., "Find me a hotel in Paris"),
  ignore the previous state and create a NEW, complete JSON for this intent.
- If the user request is a *response* (e.g., "From Paris", "on Dec 15th"),
  USE the previous JSON state and ONLY ADD or MODIFY the information provided. The intent should be 'CLARIFICATION' or the one from the previous state.
- If the user confirms a booking (e.g., "yes", "book it", "that's perfect, confirm"),
  detect the 'BOOK_ITEM' intent.
- Always report the booking_context from the previous state.

Output JSON Structure:
{
  "intent": "SEARCH_FLIGHT" | "SEARCH_HOTEL" | "BOOK_ITEM" | "CLARIFICATION",
  "parameters": {
    "location": "CITY" (or null),
    "departure_date": "YYYY-MM-DD" (or null),
    "origin": "CITY_OR_IATA_CODE" (or null),
    "destination": "CITY_OR_IATA_CODE" (or null),
    "check_in_date": "YYYY-MM-DD" (or null),
    "check_out_date": "YYYY-MM-DD" (or null)
  },
  "booking_context": {
    "item_to_book": { "type": "flight" | "hotel" | null, "id": "ITEM_ID", "price": 123.45 },
    "is_confirmed": false
  }
}
"""

nlu_generation_config = {
    "temperature": 0.0,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

MODEL_NAME_TO_USE = "gemini-2.5-flash"

# NLU Model Initialization
llm_nlu = genai.GenerativeModel(
    model_name=MODEL_NAME_TO_USE,
    generation_config=nlu_generation_config,
    system_instruction=NLU_SYSTEM_PROMPT
)

# --- NLG BRAIN (Phase 2) ---
# This system prompt remains unchanged from v2.1 (it already handles errors)
NLG_SYSTEM_PROMPT = """
You are a conversational, friendly, and helpful travel agent.
Your task is to respond to the user based on the context provided.

- Always be friendly and use a natural, engaging tone.
- If the conversation state is incomplete, politely ask for the missing single piece of information.

- If 'task_results' contains an error (e.g., {"error": "NO_RESULTS"}):
    - Acknowledge the search but apologize for the lack of results.
    - If the error is 'NO_RESULTS', suggest searching again with a slightly different query or date.
    - If the error is 'SERVICE_ERROR', apologize and suggest retrying later or choosing an alternative service.

- If 'task_results' contains successful results (e.g., flight at 650 EUR):
    - Present the best result clearly.
    - ALWAYS finish by asking a confirmation question to book it.
    - (Example: "I found an Air France flight for 650€. Would you like me to book it?")

- If a booking was just confirmed (task_results status is "BOOKING_CONFIRMED"):
    - Confirm the booking to the user and include the confirmation code.
    - (Example: "It's done! Your flight to Montreal is confirmed. Your code is XYZ123.")
"""

nlg_generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

# NLG Model Initialization
llm_nlg = genai.GenerativeModel(
    model_name=MODEL_NAME_TO_USE,
    generation_config=nlg_generation_config,
    system_instruction=NLG_SYSTEM_PROMPT
)


# --- 2. AGENT FUNCTIONS ---

def clean_json_string(s):
    """
    Cleans the raw LLM output to keep only the valid JSON.
    (Unchanged from v2.1)
    """
    start_index = s.find('{')
    end_index = s.rfind('}')

    if start_index != -1 and end_index != -1 and end_index > start_index:
        return s[start_index:end_index + 1]

    print(f"--- NLU WARNING: Could not clean JSON ---")
    print(f"Raw Response: {s}")
    return None


# --- NEW: TASK SIGNING FUNCTION (Task 2) ---
def _sign_task(task_object):
    """
    Signs a task object using the agent's private key (Ed25519)
    and returns it in the new Zero-Trust format.
    """
    if not task_object:
        return None

    try:
        # 1. Serialize the task object into a canonical JSON string.
        # sort_keys=True ensures the key order is always the same.
        # separators=(',', ':') removes whitespace for a compact representation.
        # This is CRITICAL for a consistent signature.
        task_json = json.dumps(task_object, sort_keys=True, separators=(',', ':')).encode('utf-8')

        # 2. Sign the serialized JSON bytes using the loaded private key
        signature = AGENT_PRIVATE_KEY.sign(task_json)

        # 3. Encode the binary signature in Base64 for safe JSON transport
        signature_b64 = base64.b64encode(signature).decode('utf-8')

        # 4. Wrap the original task and signature in the new format
        signed_task_wrapper = {
            "task": task_object,
            "signature": signature_b64,
            "algorithm": "Ed25519"  # As specified in the brief
        }

        print(f"--- INFO: Task successfully signed (Sig: {signature_b64[:10]}...) ---")
        return signed_task_wrapper

    except Exception as e:
        print(f"--- CRITICAL SIGNING ERROR ---")
        print(f"Failed to sign task: {e}")
        # If signing fails, we must not send the task.
        return None


# --- END NEW FUNCTION ---


def nlu_phase_llm(user_prompt, previous_state):
    """
    Phase 0: NLU (Natural Language Understanding) - v3.0
    (Unchanged from v2.1)
    """
    print("--- 0. NLU PHASE (v3.0 NLU Brain) ---")
    print(f"User prompt: \"{user_prompt}\"")

    nlu_context = f"""
    Previous JSON State:
    {json.dumps(previous_state, indent=2)}
    Current User Request:
    "{user_prompt}"
    Updated JSON:
    """

    print(f"Contacting Gemini API (NLU) with model '{MODEL_NAME_TO_USE}'...")

    try:
        response = llm_nlu.generate_content(nlu_context)
        raw_text = response.text
    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR during NLU Phase ---")
        print(f"Error: {e}")
        return previous_state

    json_string = clean_json_string(raw_text)
    if not json_string:
        print(f"--- NLU ERROR: Non-JSON or malformed response received ---")
        print(f"Raw Response: {raw_text}")
        return previous_state

    try:
        updated_state = json.loads(json_string)

        # Persistence logic for the booking context
        if previous_state.get("booking_context", {}).get("item_to_book") and \
                not updated_state.get("booking_context", {}).get("item_to_book") and \
                updated_state.get("intent") != "BOOK_ITEM":
            print("--- INFO: Manually reporting 'item_to_book' in state.")
            if "booking_context" not in updated_state:
                updated_state["booking_context"] = {}
            updated_state["booking_context"]["item_to_book"] = previous_state["booking_context"]["item_to_book"]

        print("Intent successfully updated:")
        print(json.dumps(updated_state, indent=2))
        return updated_state
    except json.JSONDecodeError:
        print(f"--- NLU ERROR: Invalid JSON after cleanup ---")
        print(f"Cleaned JSON (attempt): {json_string}")
        return previous_state


def core_processing_phase(conversation_state):
    """
    Phase 1: Core Processing (Task Preparation) - v3.0
    MODIFIED: All task objects are now passed to _sign_task before being returned.
    """
    print("\n--- 1. CORE PROCESSING PHASE (v3.0 Task Prep & Sign) ---")

    if not conversation_state or "intent" not in conversation_state:
        print("Error: Invalid or unrecognized intent.")
        return None

    intent = conversation_state.get("intent")
    params = conversation_state.get("parameters", {})
    booking_context = conversation_state.get("booking_context", {})

    task_to_perform = None  # This is the "inner" task object

    # Routing logic based on intent
    if intent == "SEARCH_FLIGHT":
        origin = params.get("origin")
        destination = params.get("destination")
        date = params.get("departure_date")

        if not all([origin, destination, date]):
            print("Required entities (Flight) missing. Requesting clarification.")
            return None  # No task, NLG will ask

        search_query = f"price flight {origin} to {destination} on {date}"

        print(f"Preparing task (Flight) with query: '{search_query}'")
        task_to_perform = {
            "task_name": "GOOGLE_SEARCH_FLIGHT",
            "query": search_query
        }

    elif intent == "SEARCH_HOTEL":
        location = params.get("location")
        check_in = params.get("check_in_date")
        check_out = params.get("check_out_date")

        if not all([location, check_in, check_out]):
            print("Required entities (Hotel) missing. Requesting clarification.")
            return None  # No task, NLG will ask

        search_query = f"price hotel {location} from {check_in} to {check_out}"

        print(f"Preparing task (Hotel) with query: '{search_query}'")
        task_to_perform = {
            "task_name": "GOOGLE_SEARCH_HOTEL",
            "query": search_query
        }

    elif intent == "BOOK_ITEM":
        item = booking_context.get("item_to_book")
        is_confirmed = booking_context.get("is_confirmed", False)

        if item and is_confirmed:
            print(f"Preparing task (Booking) for item: {item.get('id')}")
            task_to_perform = {
                "task_name": f"BOOK_{item.get('type').upper()}",  # ex: BOOK_FLIGHT
                "item_id": item.get("id"),
                "price": item.get("price")
            }
        else:
            print("Booking intent detected, but item or confirmation is missing.")
            return None

    elif intent == "CLARIFICATION":
        print("Clarification intent. No task to execute.")
        return None

    else:
        print(f"Intent '{intent}' not handled by Core Processing.")
        return None

    # --- NEW: FINAL SIGNING STEP ---
    # All tasks are signed before being returned to the orchestrator.
    return _sign_task(task_to_perform)


def generation_phase_llm(task_results, user_prompt, conversation_state):
    """
    Phase 2: Generation (NLG) - v3.0
    (Unchanged from v2.1)
    """
    print("\n--- 2. GENERATION PHASE (v3.0 NLG Brain) ---")

    context = f"""
    Original User Prompt: "{user_prompt}"
    Current Conversation State (JSON parsed by NLU):
    {json.dumps(conversation_state, indent=2)}
    Task Results (provided by external tool):
    {json.dumps(task_results, indent=2) if task_results else "null"}
    Your Response:
    """

    print(f"Contacting Gemini API (NLG) with model '{MODEL_NAME_TO_USE}'...")

    try:
        response = llm_nlg.generate_content(context)
        final_response = response.text
        print("Response successfully generated.")
        return final_response

    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR during NLG Phase ---")
        print(f"Error: {e}")
        return "I'm sorry, an internal error occurred while generating my response."


# --- 3. MAIN EXECUTION FUNCTIONS ---

def initialize_agent():
    """
    Called once at startup.
    (Unchanged from v2.1)
    """
    conversation_state = {
        "intent": "CLARIFICATION",
        "parameters": {},
        "booking_context": {"item_to_book": None, "is_confirmed": False}
    }
    return conversation_state


def run_agent_turn(user_input, current_state):
    """
    Executes a single turn of conversation.
    Returns: (agent_response_text, new_state, signed_task_wrapper)
    (Unchanged from v2.1, but the task it returns is now signed)
    """

    # Phase 0: NLU (State Update)
    conversation_state = nlu_phase_llm(user_input, current_state)

    if not conversation_state:
        response = "I'm sorry, I could not process that request."
        return response, current_state, None

    # Phase 1: Core Processing (Task Preparation & Signing)
    # This now returns the new signed task format: {"task": {...}, "signature": "..."}
    signed_task = core_processing_phase(conversation_state)

    # --- ORCHESTRATOR CHECKPOINT ---
    if signed_task:
        print("--- TASK REQUIRED CHECKPOINT ---")
        print(f"Agent requested execution of: {signed_task['task']['task_name']}")
        return None, conversation_state, signed_task

    # Phase 2: Generation (if NO task is required)
    task_results = None
    final_response = generation_phase_llm(task_results, user_input, conversation_state)

    return final_response, conversation_state, None

