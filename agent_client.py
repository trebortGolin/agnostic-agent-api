# --- Imports ---
# 1. Import 'httpx', our code "browser" for calling APIs
# 2. Import 'json' to format the response nicely
import httpx
import json

# --- Define our "Intent" (The Request) ---

# This is the JSON our AC (Agent Client) will send.
# It MUST match the 'IntentRequest' structure defined in the AF (Agent Supplier).
intent_request_data = {
    "transactionId": "uuid-client-AC-001",
    "requesterId": "urn:ac:my-dev-client:test:001",
    "serviceType": "booking:flight",
    "intent": {
        "params": {
            "from": "CDG",
            "to": "JFK",
            "date": "2025-11-15"
        },
        "constraints": {
            "maxPrice": 500,
            "currency": "EUR"
        }
    }
}

# The address of our Agent Supplier (which we launched in Step 1)
# This is the full URL of the 'negotiate' endpoint
SUPPLIER_URL = "http://127.0.0.1:8000/atp/v1/negotiate"


# --- The Main Function (The Action) ---

def run_agent_client():
    """
    Runs the client: sends the intent and prints the response.
    """
    print(f"--- AGENT CLIENT (AC) STARTED ---")
    print(f"Sending intent to: {SUPPLIER_URL}")
    print("Data sent:")
    print(json.dumps(intent_request_data, indent=2))
    print("----------------------------------\n")

    try:
        # 'httpx.post(...)' : This is the action!
        # 1. URL: Where to send the request
        # 2. json=... : 'httpx' converts our Python dictionary to JSON
        # 3. timeout=10.0 : Safety (we don't wait more than 10s)
        response = httpx.post(SUPPLIER_URL, json=intent_request_data, timeout=10.0)

        # --- Response Processing ---

        # 'raise_for_status()' : Checks for an HTTP error (e.g., 404, 500)
        # If so, the script stops here.
        response.raise_for_status()

        # If everything is fine (code 200):
        print(f"\n--- RESPONSE RECEIVED FROM AF (Code: {response.status_code}) ---")

        # 'response.json()' : Re-converts the JSON response into a Python dictionary
        offer_response = response.json()

        # We print the response nicely
        print(json.dumps(offer_response, indent=2))

        # We extract specific data
        if offer_response.get("offers"):
            offer_price = offer_response["offers"][0].get("price")
            # The one remaining French string is EUR, which is a currency code, so it stays.
            print(f"\nSuccess! The AF offered us a flight at {offer_price} EUR.")

    except httpx.HTTPStatusError as e:
        # Error if the server returns 4xx or 5xx
        print(f"\n--- HTTP ERROR ---")
        print(f"The AF returned an error: {e.response.status_code}")
        print(f"Details: {e.response.text}")
    except httpx.RequestError as e:
        # Error if the server is unreachable (e.g., not launched)
        print(f"\n--- CONNECTION ERROR ---")
        print(f"Could not contact the Agent Supplier at {e.request.url!r}.")
        print("Did you remember to run 'agent_fournisseur.py' in the other terminal?")
    except json.JSONDecodeError:
        # Error if the AF returns text that is not valid JSON
        print(f"\n--- PROTOCOL ERROR ---")
        print("The AF returned a response that is not valid JSON.")
        print(f"Raw response: {response.text}")


# --- Script entry point ---
if __name__ == "__main__":
    run_agent_client()

