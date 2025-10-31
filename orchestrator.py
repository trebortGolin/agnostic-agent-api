# --- ORCHESTRATOR (v2.4 - Production Logging) ---
# This script transforms the orchestrator into a Flask Web API server.
# v2.4: Implements production-level logging for tracking requests, errors, and tasks.

import json
import agent_client as agent  # Imports our agent brain
import logging  # New: Standard Python logging module
from flask import Flask, request, jsonify

# --- LOGGING CONFIGURATION ---
# Configure logging to output detailed information to the console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Initialize the Flask application
app = Flask(__name__)


# --- Helper Functions (Same as v2.1) ---
def _update_state_from_results(conversation_state, task_results):
    """
    Updates the conversation_state (agent's memory) based on the results
    of an external task (search or booking).
    """
    # Only update state if the task was a SUCCESS
    if task_results and "error" not in task_results:

        if task_results.get("search_type") == "FLIGHT":
            # A flight search was successful. Memorize the item for a future booking.
            best_result = task_results.get("results", [{}])[0]
            if best_result.get("item_id"):
                conversation_state["booking_context"] = {
                    "item_to_book": {"type": "flight", "id": best_result.get("item_id"),
                                     "price": best_result.get("price")},
                    "is_confirmed": False
                }
        elif task_results.get("search_type") == "HOTEL":
            # A hotel search was successful. Memorize the item for a future booking.
            best_result = task_results.get("results", [{}])[0]
            if best_result.get("item_id"):
                conversation_state["booking_context"] = {
                    "item_to_book": {"type": "hotel", "id": best_result.get("item_id"),
                                     "price": best_result.get("price")},
                    "is_confirmed": False
                }
        elif task_results.get("status") == "BOOKING_CONFIRMED":
            # The booking was confirmed. Clear the context.
            conversation_state["booking_context"] = {"item_to_book": None, "is_confirmed": False}

    return conversation_state


# --- 1. CONVERSATION ENDPOINT (The Agent's "Brain") ---
@app.route('/chat_turn', methods=['POST'])
def handle_chat_turn():
    """
    Executes a single turn of conversation.
    Returns either the agent's response or a task to execute.
    """
    logging.info("REQUEST RECEIVED ON /chat_turn")

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
    agent_response, new_state, task = agent.run_agent_turn(user_input, conversation_state)

    # 2. Handle the response (Task or Clarification)
    if task:
        # TASK REQUIRED
        logging.info(f"Task detected: {task['task_name']}")

        # Security logic
        if task['task_name'].startswith('BOOK_'):
            auth_token = request.headers.get('Authorization')

            if not auth_token:
                logging.error("Secure task requested but no Auth token provided.")
                error_response = "This action (booking) requires authentication. Cannot proceed."
                return jsonify({"response_text": error_response, "new_state": new_state, "task": None}), 401

            logging.info(f"Secure task, injecting Auth token: {auth_token[:15]}...")
            task['auth_token'] = auth_token

        # Returns the new state and the TASK to execute
        return jsonify({
            "response_text": None,
            "new_state": new_state,
            "task": task
        })

    else:
        # CLARIFICATION RESPONSE
        logging.info("Clarification response generated")
        return jsonify({
            "response_text": agent_response,
            "new_state": new_state,
            "task": None
        })


# --- 2. GENERATION ENDPOINT (After Task Execution) ---
@app.route('/generate_response', methods=['POST'])
def handle_generate_response():
    """
    This endpoint is called by the external orchestrator AFTER
    it has executed the task.
    v2.3 Fix: Uses .get() with defaults to ensure keys are never missing.
    """
    logging.info("REQUEST RECEIVED ON /generate_response")

    # --- v2.3 FIX: Use .get() with defaults to prevent the 'Missing data' error ---
    try:
        data = request.json
        # These fields are retrieved using .get() with robust defaults.
        # This prevents the 'Missing data' error, even if the user sends an incomplete request.
        task_results = data.get('task_results', {})
        user_prompt = data.get('user_prompt', 'Initial request failed to parse.')
        conversation_state = data.get('conversation_state', agent.initialize_agent())
    except Exception as e:
        # This catches JSON decode errors if the structure is completely broken
        logging.error(f"Critical JSON decoding failure: {e}")
        return jsonify({"error": f"Critical JSON decoding failure: {e}"}), 400

    # --- v2.1: ERROR SIMULATION LOGIC ---
    if "SIMULATE NO RESULTS" in user_prompt.upper():
        logging.warning("SIMULATION: Injecting NO_RESULTS error.")
        task_results = {"error": "NO_RESULTS"}
    elif "SIMULATE SERVICE ERROR" in user_prompt.upper():
        logging.error("SIMULATION: Injecting SERVICE_ERROR.")
        task_results = {"error": "SERVICE_ERROR", "details": "External API is down (503)."}
    # --- END ERROR SIMULATION ---

    # Update state (only happens on SUCCESS, due to logic in _update_state_from_results)
    conversation_state = _update_state_from_results(conversation_state, task_results)

    # 1. Execute Phase 2 (NLG) with the task results (which might be an error)
    final_response = agent.generation_phase_llm(task_results, user_prompt, conversation_state)

    # 2. Return the final response and the new state
    return jsonify({
        "response_text": final_response,
        "new_state": conversation_state
    })


# --- Main entry point (Same as v2.1) ---
if __name__ == "__main__":
    logging.info("ORCHESTRATOR API v2.4 (Production Logging) STARTING...")
    print("Your agent is now 'live' on http://127.0.0.1:5000")
    print("Use a tool like Postman or curl to test the endpoints.")
    app.run(debug=True, port=5000, use_reloader=False)
