Agnostic AI Agent Specialist Architecture (v3.1 - Zero-Trust)

1. Vision: The Agnostic Service Layer for the "Internet of Agents"

This project provides a robust, production-ready, zero-trust architecture for a Specialist Agent. It is designed to be the trusted, interoperable service layer for the emerging "Internet of Agents."

Its purpose is to connect any AI Orchestrator (e.g., Apple Intelligence, AutoGPT) with any specialized, secure backend service, guaranteeing identity and integrity.

Core Principles

Model-Agnostic: The "Brain" (agent_client.py) is modular. This reference implementation uses Google's Gemini, but it can be swapped out to use OpenAI (ChatGPT), Anthropic (Claude), or any other model without changing the core infrastructure.

Domain-Agnostic: The Travel Agent (handling SEARCH_FLIGHT) is only an example. This architecture is a generic protocol for any intent (ORDER_PIZZA, SCHEDULE_MEETING, etc.).

2. Architecture: Brain vs. Transport (v3.0)

The architecture strictly separates the AI logic ("The Brain") from the API and security logic ("The Transport").

agent_client.py (The Brain / The Specialist)

Contains all AI logic: Natural Language Understanding (NLU) and Natural Language Generation (NLG).

Manages conversational state (conversation_state) and multi-turn dialogue (slot-filling).

NEW (v3.0): Reads a Private Key (AGENT_PRIVATE_KEY) from environment variables.

NEW (v3.0): Cryptographically signs all outgoing tasks (e.g., BOOK_FLIGHT) using Ed25519 to ensure task integrity (prevents non-repudiation).

orchestrator.py (The Transport / The API Server)

A production-ready Flask API server (v3.0) with logging.

Completely agnostic to the AI model.

NEW (v3.0): Implements a Zero-Trust API Lock. All endpoints (/chat_turn, /generate_response, /manifest) are secured and require a valid X-ATP-Key header for access (prevents DoS/abuse).

NEW (v3.0): Handles User Authentication. It extracts the user's Authorization header during secure tasks (like BOOK_ITEM) and passes it to the Orchestrator.

agent-manifest.json (The Public Contract)

The "business card" for your agent. It tells external orchestrators what capabilities (intents) this agent supports.

NEW (v3.0): Now includes a trust section containing the Public Key and algorithm, allowing any orchestrator to verify the agent's task signatures.

3. The Zero-Trust Protocol (The JSON Contract)

Any external orchestrator must follow this two-endpoint protocol and respect the new security layers.

Security Layer 1: API Key Authentication (Task 1)

All requests to any endpoint MUST include the secret API key.
Header: "X-ATP-Key: sk-atp-xxxxxxxx"

Endpoint 1: /chat_turn (The Conversation)

Drives the conversation. Takes user input, decides what to do next.

Method: POST

Purpose: NLU & Core Logic.

Body:

{
  "user_input": "Yes, book it for me.",
  "conversation_state": { ... }
}


NEW (v3.0) Success Response (Task): Returns the signed task wrapper.

{
  "new_state": { ... },
  "response_text": null,
  "signed_task": {
    "task": {
      "task_name": "BOOK_FLIGHT",
      "item_id": "AT456",
      ...
    },
    "signature": "aV...Zw==",
    "algorithm": "Ed25519"
  },
  "user_auth_token": "Bearer user_token_abc123"
}


Endpoint 2: /generate_response (The Follow-up)

Called after the orchestrator executes a task. Generates the final human response.

Method: POST

Purpose: NLG.

Body:

{
  "task_results": { "status": "BOOKING_CONFIRMED", ... },
  "user_prompt": "Yes, book it for me.",
  "conversation_state": { ... }
}


Success Response:

{
  "new_state": { ... },
  "response_text": "It's done! Your flight is confirmed."
}


Endpoint 3: /manifest (Discovery)

Serves the agent-manifest.json file.

Method: GET

Purpose: Allows an orchestrator to discover this agent's capabilities and public key.

4. Getting Started (v3.0 Deployment)

1. Generate Keys

Run these in your terminal to create the signing keys.

# 1. Create the Private Key
openssl genpkey -algorithm Ed25519 -out agent_private_key.pem

# 2. Extract the Public Key
openssl pkey -in agent_private_key.pem -pubout -out agent_public_key.pem


2. Update Manifest

Copy the content of agent_public_key.pem and paste it into the trust.public_key field in agent-manifest.json.

3. Install Dependencies

pip install -r requirements.txt


4. Set Environment Variables

This is the new, secure configuration.

# Activate your environment
source venv/bin/activate

# 1. LLM Brain Key
export GEMINI_API_KEY="YOUR_VALID_GEMINI_KEY"

# 2. This API Server's Secret Key (Task 1)
export AGENT_API_KEY="sk-atp-a-secret-you-invent"

# 3. The Agent's Private Signing Key (Task 2)
export AGENT_PRIVATE_KEY=$(cat agent_private_key.pem)

# 4. Encoding
export PYTHONIOENCODING=UTF-8


5. Run the API Server

python orchestrator.py


Agent is now live and LOCKED on http://127.0.0.1:5000.

6. Test with Secure cURL

Test that the server is locked and requires the 'X-ATP-Key'.

curl -X POST [http://127.0.0.1:5000/chat_turn](http://127.0.0.1:5000/chat_turn) \
     -H "Content-Type: application/json" \
     -H "X-ATP-Key: sk-atp-a-secret-you-invent" \
     -d '{
           "user_input": "Je veux un vol pour Montréal",
           "conversation_state": {}
         }'
