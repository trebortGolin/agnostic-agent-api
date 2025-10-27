# --- Imports ---
import httpx
import sys
import time
import json  # To print JSON payloads nicely

# --- v0.4: Configuration ---
# The client *only* knows the address of the Directory, not the suppliers.
DIRECTORY_URL = "http://127.0.0.1:8001"
SERVICE_TO_FIND = "booking:flight"


def discover_supplier_url(client: httpx.Client, service_type: str) -> str:
    """
    v0.4: New function to call the Agent Directory and find a supplier.
    Returns the baseUrl of the first supplier found.
    """
    print(f"--- v0.4: DISCOVERY PHASE ---")
    discover_url = f"{DIRECTORY_URL}/discover"
    params = {"serviceType": service_type}

    print(f"Asking Directory ({discover_url}) for service: '{service_type}'")

    try:
        response = client.get(discover_url, params=params, timeout=5.0)
        response.raise_for_status()  # Check for errors (like 404)

        data = response.json()

        if not data.get("suppliers"):
            print(f"Discovery FAILED: No suppliers found for '{service_type}'")
            return None

        # Success! Get the URL of the first supplier.
        supplier_url = data["suppliers"][0]["baseUrl"]
        supplier_name = data["suppliers"][0]["name"]

        print(f"Discovery SUCCESS: Found '{supplier_name}' at: {supplier_url}")
        print("-" * 40 + "\n")
        return supplier_url

    except httpx.ConnectError:
        print(f"\n--- CLIENT ERROR ---")
        print(f"Connection failed: Could not connect to Directory at {DIRECTORY_URL}.")
        print("Are you sure 'agent_directory.py' is running on port 8001?")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\n--- CLIENT ERROR ---")
        print(f"HTTP Error: The Directory responded with a {e.response.status_code} status.")
        print(f"Response body: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR during Discovery ---")
        print(f"An error occurred: {e}")
        sys.exit(1)


def run_test_1_success_and_commit(client: httpx.Client, supplier_base_url: str):
    """
    v0.4: Runs the full negotiation AND commit flow.
    Now uses the dynamically discovered supplier_base_url.
    """
    print("--- RUNNING TEST 1 (EXPECTING SUCCESS + COMMIT) ---")

    negotiate_payload = {
        "transactionId": "uuid-client-AC-006",  # New TX ID
        "requesterId": "urn:ac:my-dev-client:test:004",
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

    negotiation_url = f"{supplier_base_url}/atp/v1/negotiate"

    try:
        # --- 1.2: Send Negotiation Request ---
        print(f"Sending Negotiation to: {negotiation_url}")
        print(f"Payload: {json.dumps(negotiate_payload, indent=2)}\n")

        response = client.post(negotiation_url, json=negotiate_payload, timeout=5.0)
        response.raise_for_status()

        response_data = response.json()
        print(f"--- NEGOTIATION RESPONSE RECEIVED (Code: {response.status_code}) ---")
        print(f"{json.dumps(response_data, indent=2)}\n")

        # --- 1.3: Check for Offer and Prepare Commit ---
        if response_data.get("offers"):
            offer = response_data["offers"][0]
            offer_id = offer.get("offerId")
            commit_endpoint = offer.get("commitEndpoint")

            print(f"TEST RESULT: SUCCESS! AS sent offer {offer_id}")

            # --- 1.4: Send Commit Request ---
            commit_payload = {
                "transactionId": negotiate_payload["transactionId"],
                "offerId": offer_id
            }

            commit_url = f"{supplier_base_url}{commit_endpoint}"

            print(f"\nSending Commit to: {commit_url}")
            print(f"Payload: {json.dumps(commit_payload, indent=2)}\n")

            commit_response = client.post(commit_url, json=commit_payload, timeout=5.0)
            commit_response.raise_for_status()

            commit_data = commit_response.json()
            print(f"--- COMMIT RESPONSE RECEIVED (Code: {commit_response.status_code}) ---")
            print(f"{json.dumps(commit_data, indent=2)}\n")

            print("--- v0.4 FULL FLOW COMPLETE ---")
            print(f"STATUS: {commit_data.get('status')}")
            print(f"Confirmation ID: {commit_data.get('confirmationId')}")

        elif response_data.get("rejections"):
            rejection = response_data["rejections"][0]
            print(f"TEST RESULT: REJECTED! AS sent rejection.")
            print(f"Reason: {rejection.get('reasonCode')} - {rejection.get('message')}")

    except httpx.ConnectError:
        print(f"\n--- CLIENT ERROR ---")
        print(f"Connection failed: Could not connect to Supplier at {supplier_base_url}.")
        print("Are you sure 'agent_supplier.py' is running on port 8000?")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\n--- CLIENT ERROR ---")
        print(f"HTTP Error: The Supplier responded with a {e.response.status_code} status.")
        print(f"Response body: {e.response.text}")
        sys.exit(1)

    print("-" * 40 + "\n")


def run_test_2_rejection(client: httpx.Client, supplier_base_url: str):
    """
    v0.4: Runs the rejection test case.
    Now uses the dynamically discovered supplier_base_url.
    """
    print("--- RUNNING TEST 2 (EXPECTING REJECTION) ---")

    intent_reject_payload = {
        "transactionId": "uuid-client-AC-007",  # New TX ID
        "requesterId": "urn:ac:my-dev-client:test:004",
        "serviceType": "booking:flight",
        "intent": {
            "params": {
                "from": "CDG",
                "to": "JFK",
                "date": "2025-11-15"
            },
            "constraints": {
                "maxPrice": 400,  # This price (400) is < OUR_PRICE (480)
                "currency": "EUR"
            }
        }
    }

    negotiation_url = f"{supplier_base_url}/atp/v1/negotiate"

    try:
        response = client.post(negotiation_url, json=intent_reject_payload, timeout=5.0)
        response.raise_for_status()
        response_data = response.json()

        print(f"--- NEGOTIATION RESPONSE RECEIVED (Code: {response.status_code}) ---")

        if response_data.get("rejections"):
            rejection = response_data["rejections"][0]
            print(f"TEST RESULT: REJECTED! AS sent rejection.")
            print(f"Reason: {rejection.get('reasonCode')} - {rejection.get('message')}")
        else:
            print(f"TEST RESULT: FAILED! Expected a rejection but got: {response_data}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print("-" * 40 + "\n")


def main():
    """
    Main function to run the v0.4 Agent Client tests.
    1. Discover the supplier.
    2. Run tests against that supplier.
    """

    # We use a single, persistent client session
    with httpx.Client() as client:
        # 1. Discover the supplier URL
        supplier_url = discover_supplier_url(client, SERVICE_TO_FIND)

        if not supplier_url:
            print("Exiting due to discovery failure.")
            sys.exit(1)

        # 2. Run Test 1 (Success + Commit)
        run_test_1_success_and_commit(client, supplier_url)

        time.sleep(1)  # Pause for cleaner logs

        # 3. Run Test 2 (Rejection)
        run_test_2_rejection(client, supplier_url)


# --- Run the Script ---
if __name__ == "__main__":
    main()

