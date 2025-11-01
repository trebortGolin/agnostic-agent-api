# --- ORCHESTRATOR (v3.1 - Secure + Logging + Fix) ---
# Merges Athena's v3.0 Zero-Trust security with v2.4 Production Logging.
# v3.1: Fixes a critical signature integrity flaw. The orchestrator
#       NO LONGER modifies the signed task payload.

import json
import agent_client as agent  # Imports our agent brain (v3.0)
import logging
import os
from functools import wraps  # For creating the auth decorator

from flask import Flask, request, jsonify, g

# --- 1. LOGGING & APP CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Initialize the Flask application
app = Flask(__name__)

# --- NEW: v3.0 SECURITY CONFIGURATION (Task 1) ---
try:
    # This is the secret key this API server uses to authenticate
    # incoming requests from external orchestrators (e.g., Apple).
    AGENT_API_KEY = os.environ.get("AGENT_API_KEY")
    if not AGENT_API_KEY:
        raise ValueError("The AGENT_API_KEY environment variable is not set.")

    # Load the agent manifest file to serve it
    with open("agent-manifest.json", "r") as f:
        AGENT_MANIFEST_CONTENT = json.load(f)

except Exception as e:
    logging.critical(f"--- CRITICAL STARTUP ERROR ---")
    logging.critical(f"Error: {e}")
    logging.critical("Please set AGENT_API_KEY and ensure agent-manifest.json exists.")
    exit()


# --- END NEW CONFIG ---


# --- 2. AUTHENTICATION DECORATOR (Task 1) ---
def require_api_key(f):
    """
    Decorator to protect endpoints.
    Checks for a valid 'X-ATP-Key' header.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-ATP-Key')

        if not api_key:
            logging.warning("AUTH_FAILURE: Request received without 'X-ATP-Key' header.")
            return jsonify({"error": "Unauthorized. 'X-ATP-Key' header is missing."}), 401

        if api_key != AGENT_API_KEY:
            logging.warning(f"AUTH_FAILURE: Invalid API Key received: {api_key[:5]}...")
            return jsonify({"error": "Forbidden. Invalid API Key."}), 403

        # Store the authenticated key source for logging
        g.auth_source = f"Orchestrator (Key: {api_key[:5]}...)"
        logging.info(f"AUTH_SUCCESS: Valid key received from {g.auth_source}")

        return f(*args, **kwargs)

    return decorated_function


# --- END DECORATOR ---


# --- Helper Function (Unchanged) ---
def _update_state_from_results(conversation_state, task_results):
    """
    Updates the conversation_state (agent's memory) based on the results
    of an external task (search or booking).
    """
    # Only update state if the task was a SUCCESS
    if task_results and "error" not in task_results:

        if task_results.get("search_type") == "FLIGHT":
            best_result = task_results.get("results", [{}])[0]
            if best_result.get("item_id"):
                conversation_state["booking_context"] = {
                    "item_to_book": {"type": "flight", "id": best_result.get("item_id"),
                                     "price": best_result.get("price")},
                    "is_confirmed": False
                }
        elif task_results.get("search_type") == "HOTEL":
            best_result = task_results.get("results", [{}])[0]
            if best_result.get("item_id"):
                conversation_state["booking_context"] = {
                    "item_to_book": {"type": "hotel", "id": best_result.get("item_id"),
                                     "price": best_result.get("price")},
                    "is_confirmed": False
                }
        elif task_results.get("status") == "BOOKING_CONFIRMED":
            conversation_state["booking_context"] = {"item_to_book": None, "is_confirmed": False}

    return conversation_state


# --- 3. API ENDPOINTS (NOW SECURED) ---

# --- NEW: MANIFEST ENDPOINT (Task 1) ---
@app.route('/manifest', methods=['GET'])
@require_api_key  # SECURED
def get_manifest():
    """
    Serves the agent-manifest.json file.
    An orchestrator must authenticate *first* to even *see* the manifest.
    """
    logging.info(f"Serving manifest to {g.auth_source}")
    return jsonify(AGENT_MANIFEST_CONTENT)


# --- END NEW ENDPOINT ---

@app.route('/chat_turn', methods=['POST'])
@require_api_key  # SECURED (Task 1)
def handle_chat_turn():
    """
    Executes a single turn of conversation.
    Returns either the agent's response or a (now signed) task.
    """
    logging.info(f"REQUEST RECEIVED ON /chat_turn from {g.auth_source}")

    try:
        data = request.json
        user_input = data.get('user_input')
        conversation_state = data.get('conversation_state', agent.initialize_agent())
    except Exception as e:
        logging.error(f"JSON decoding error: {e}")
        return jsonify({"error": f"JSON decoding error: {e}"}), 400

    if not user_input:
        logging.warning("user_input missing in request.")
        return jsonify({"error": "user_input missing"}), 400

    # 1. Execute the agent (Phases 0 and 1)
    # agent_client (v3.0) now returns a SIGNED task
    agent_response, new_state, signed_task = agent.run_agent_turn(user_input, conversation_state)

    # 2. Handle the response (Task or Clarification)
    if signed_task:
        # TASK REQUIRED
        logging.info(f"Task detected: {signed_task['task']['task_name']}")

        # --- MODIFIED v3.1: Security logic ---
        if signed_task['task']['task_name'].startswith('BOOK_'):
            # The 'auth_token' here is for the *downstream* service (e.g., Amadeus)
            # The 'X-ATP-Key' was for the *upstream* service (Apple -> Us)
            user_auth_token = request.headers.get('Authorization')  # Get the user's token

            if not user_auth_token:
                logging.error("Secure task BOOK_ITEM missing user 'Authorization' header.")
                error_response = "This action (booking) requires user authentication. Please provide an 'Authorization' header."
                return jsonify({"response_text": error_response, "new_state": new_state, "task": None}), 401

            # --- FIX v3.1 ---
            # The bug we found in the previous test is fixed here.
            # We NO LONGER modify the signed_task.
            # --- END FIX ---

            logging.info(f"Secure task, returning signed task AND user auth token separately.")

            return jsonify({
                "response_text": None,
                "new_state": new_state,
                "signed_task": signed_task,  # The agent's *unmodified* signed payload
                "user_auth_token": user_auth_token  # The user's token for the *next* hop
            })
        # --- END MODIFIED v3.1 ---

        # Returns the new state and the SIGNED task (for non-secure tasks)
        return jsonify({
            "response_text": None,
            "new_state": new_state,
            "signed_task": signed_task,
            "user_auth_token": None  # No user auth needed for non-booking tasks
        })

    else:
        # CLARIFICATION RESPONSE
        logging.info("Clarification response generated")
        return jsonify({
            "response_text": agent_response,
            "new_state": new_state,
            "signed_task": None,
            "user_auth_token": None
        })


@app.route('/generate_response', methods=['POST'])
@require_api_key  # SECURED (Task 1)
def handle_generate_response():
    """
    This endpoint is called by the external orchestrator AFTER
    it has executed the task.
    """
    logging.info(f"REQUEST RECEIVED ON /generate_response from {g.auth_source}")

    try:
        data = request.json
        # v3.1 Robustness: Use .get() to avoid KeyErrors
        task_results = data.get('task_results', {})
        user_prompt = data.get('user_prompt')
        conversation_state = data.get('conversation_state')

        # v3.1 Robustness Check
        if not all([task_results is not None, user_prompt, conversation_state is not None]):
            logging.error(
                f"Incomplete data received: task_results={task_results}, user_prompt={user_prompt}, state_exists={conversation_state is not None}")
            return jsonify({"error": "Missing data (task_results, user_prompt, or conversation_state)"}), 400

    except Exception as e:
        logging.error(f"Critical JSON decoding failure: {e}")
        return jsonify({"error": f"Critical JSON decoding failure: {e}"}), 400

    # --- v3.0: ERROR SIMULATION LOGIC ---
    if "SIMULATE NO RESULTS" in user_prompt.upper():
        logging.warning("SIMULATION: Injecting NO_RESULTS error.")
        task_results = {"error": "NO_RESULTS"}
    elif "SIMULATE SERVICE ERROR" in user_prompt.upper():
        logging.error("SIMULATION: Injecting SERVICE_ERROR.")
        task_results = {"error": "SERVICE_ERROR", "details": "External API is down (503)."}
    # --- END ERROR SIMULATION ---

    # Update state (only happens on SUCCESS)
    conversation_state = _update_state_from_results(conversation_state, task_results)

    # 1. Execute Phase 2 (NLG) with the task results
    final_response = agent.generation_phase_llm(task_results, user_prompt, conversation_state)

    # 2. Return the final response and the new state
    return jsonify({
        "response_text": final_response,
        "new_state": conversation_state
    })


# --- Main entry point ---
if __name__ == "__main__":
    logging.info("ORCHESTRATOR API v3.1 (Zero-Trust + Fix) STARTING...")
    print(f"--- ORCHESTRATOR API v3.1 (Zero-Trust + Fix) ---")
    print(f"--- INFO: This server is LOCKED and requires a valid 'X-ATP-Key' header. ---")
    print(f"Your agent is now 'live' on http://127.0.0.1:5000")
    print("Use a tool like Postman or curl to test the endpoints.")
    # use_reloader=False is important for stability when loading keys
    app.run(debug=True, port=5000, use_reloader=False)

