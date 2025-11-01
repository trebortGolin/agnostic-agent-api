# 🤖 Agnostic AI Agent Specialist Architecture (v3.3 - Zero-Trust)

## 1. 🎯 Vision: The Agnostic Service Layer for the "Internet of Agents"

This project provides a robust, **production-ready, zero-trust** architecture for a Specialist Agent. It is designed to be the trusted, interoperable service layer for the emerging "Internet of Agents."

Its purpose is to connect any AI Orchestrator (e.g., Apple Intelligence, AutoGPT) with any specialized, secure backend service, guaranteeing **identity** and **integrity**.

### Core Principles

* **🔄 Model-Agnostic:** The "Brain" (`agent_client.py`) is modular. This reference implementation uses Google's Gemini, but it can be swapped out to use OpenAI (ChatGPT), Anthropic (Claude), or any other model without changing the core infrastructure.

* **✈️ Domain-Agnostic:** The Travel Agent (handling `SEARCH_FLIGHT`) is only an example. This architecture is a generic protocol for any intent (`ORDER_PIZZA`, `SCHEDULE_MEETING`, etc.).

## 2. 🏗️ Architecture: Brain vs. Transport (v3.0)

The architecture strictly separates the AI logic ("The Brain") from the API and security logic ("The Transport").

### `agent_client.py` (🧠 The Brain / The Specialist)

* Contains all AI logic: Natural Language Understanding (NLU) and Natural Language Generation (NLG).
* Manages conversational state (`conversation_state`) and multi-turn dialogue (slot-filling).
* **NEW (v3.0):** Reads a **Private Key** (`AGENT_PRIVATE_KEY`) from environment variables.
* **NEW (v3.0):** Cryptographically **signs** all outgoing tasks (e.g., `BOOK_FLIGHT`) using Ed25519 to ensure task integrity (prevents non-repudiation).

### `orchestrator.py` (🛡️ The Transport / The API Server)

* A production-ready Flask API server (v3.0) with logging.
* Completely agnostic to the AI model.
* **NEW (v3.0):** Implements a **Zero-Trust API Lock**. All endpoints (`/chat_turn`, `/generate_response`, `/manifest`) are **secured** and require a valid `X-ATP-Key` header for access (prevents DoS/abuse).
* **NEW (v3.0):** Handles **User Authentication**. It extracts the user's `Authorization` header during secure tasks (like `BOOK_ITEM`) and passes it to the Orchestrator.

### `agent-manifest.json` (📜 The Public Contract)

* The "business card" for your agent. It tells external orchestrators what capabilities (intents) this agent supports.
* **NEW (v3.0):** Now includes a `trust` section containing the **Public Key** and algorithm, allowing any orchestrator to verify the agent's task signatures.

## 3. 🔒 The Zero-Trust Protocol (The JSON Contract)

Any external orchestrator must follow this two-endpoint protocol and respect the new security layers.

### **🔑 Security Layer 1: API Key Authentication (Task 1)**

All requests to *any* endpoint MUST include the secret API key.
`Header: "X-ATP-Key: sk-atp-xxxxxxxx"`

---

### 🗣️ Endpoint 1: `/chat_turn` (The Conversation)

Drives the conversation. Takes user input, decides what to do next.

* **Method:** `POST`
* **Purpose:** NLU & Core Logic.
* **Body:**
    ```json
    {
      "user_input": "Yes, book it for me.",
      "conversation_state": { ... }
    }
    ```
* **NEW (v3.0) Success Response (Task):** Returns the **signed task wrapper**.
    ```json
    {
      "new_state": { ... },
      "response_text": null,
      "signed_task": {
        "task": {
          "task_name": "BOOK_FLIGHT",
          "item_id": "AT456",
          "..." : "..."
        },
        "signature": "aV...Zw==",
        "algorithm": "Ed25519"
      },
      "user_auth_token": "Bearer user_token_abc123"
    }
    ```

---

### 📩 Endpoint 2: `/generate_response` (The Follow-up)

Called *after* the orchestrator executes a task. Generates the final human response