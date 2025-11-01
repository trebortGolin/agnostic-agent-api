amorce (SDK v1.0)Reference implementation (Python / Flask) of the Agnostic Transaction Protocol (ATP).This project provides the v1.0 SDK for the amorce agent, a "Zero-Trust" secure API designed to expose an LLM in a controlled and verifiable manner.ArchitectureThis repository is designed to be deployed as a containerized service (e.g., on Google Cloud Run) using the provided Dockerfile.orchestrator.py: The API layer (Flask). It handles authentication (X-ATP-Key), schema validation, and signature verification. This is the "lock".agent_client.py: The logic layer (the "brain"). It manages business logic, task execution, and calls to the LLM.agent-manifest.json: The agent's public contract, compliant with the ATP specification.Security Model (Zero-Trust)Security is managed at two levels:Authentication (The Lock): The orchestrator blocks any request lacking a valid X-ATP-Key header (via the AGENT_API_KEY variable).Integrity (The Seal): The agent cryptographically signs all its responses (signed_task) using its private key (via the AGENT_PRIVATE_KEY variable). The client can then verify this signature using the public key provided in the /manifest.Quick Start (Local)1. PrerequisitesPython 3.11+ (to match the production Dockerfile)A virtual environment (venv)2. Installation# Clone the repository
git clone [https://github.com/trebortgolin/amorce.git](https://github.com/trebortgolin/amorce.git)
cd amorce

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the dependencies
pip install -r requirements.txt
3. Configuration (Environment Variables)The application is designed to "fail-fast" and will refuse to start if these variables are not set.Create a .env file at the project root, or export these variables:# .env

# 1. The API "lock" (used by orchestrator.py)
# Secret key to authenticate with the API (must be in the X-ATP-Key header)
AGENT_API_KEY="sk-atp-amorce-dev-..."

# 2. The agent "seal" (used by agent_client.py)
# Path (or content) of the Ed25519 private key used to sign responses.
AGENT_PRIVATE_KEY="agent_private_key.pem"

# 3. The LLM "brain" (used by agent_client.py)
# API key for Google Gemini, as our agent_client uses google-generativeai
GEMINI_API_KEY="AIzaSy..."
4. Generate Keys (if they don't exist)Ensure you have agent_private_key.pem and agent_public_key.pem files at the root. Our code (agent_client.py) uses the Ed25519 standard (not RSA).# (Generate the Ed25519 private key)
openssl genpkey -algorithm Ed25519 -out agent_private_key.pem

# (Extract the corresponding public key)
openssl pkey -in agent_private_key.pem -pubout -out agent_public_key.pem
(Don't forget to copy the content of agent_public_key.pem into your agent-manifest.json)5. Launch (Local)# Launch the Flask development server (local)
flask --app orchestrator run --port 5000
Deployment (Production)This project is designed for containerized deployment. The provided Dockerfile handles the configuration.The command used by the Dockerfile to launch the server in production is:# Command (used in the Dockerfile)
flask run --host=0.0.0.0 --port=5000
