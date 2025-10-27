# --- Imports ---
import httpx
import sys
import time
import json  # To print JSON payloads nicely

# --- Configuration ---
# v0.3: We now define the BASE URL, as we will call two endpoints
BASE_SUPPLIER_URL = "http://127.0.0.1:8000"
NEGOTIATE_ENDPOINT = "/atp/v1/negotiate"


# Note: In a real app, the client would *discover* the commit endpoint
# from the offer response, but we'll hardcode the path structure for now.

def run_test_1_success_and_commit():
    """
    v0.3: Runs the full negotiation AND commit flow.
    """
    print("--- RUNNING TEST 1 (EXPECTING SUCCESS + COMMIT) ---")

    # --- 1.1: Negotiation Payload ---
    negotiate_payload = {
        "transactionId": "uuid-client-AC-004",  # New transaction ID for v0.3 test
        "requesterId": "urn:ac:my-dev-client:test:003",
        "serviceType": "booking:flight",
        "intent": {
            "params": {
                "from": "CDG",
                "to": "JFK",
                "date": "2025-11-15"
            },
            "constraints": {
                "maxPrice": 500,  # This price (500) is > OUR_PRICE (480)
                "currency": "EUR"
            }
        }
    }

    negotiation_url = f"{BASE_SUPPLIER_URL}{NEGOTIATE_ENDPOINT}"

    try:
        # --- 1.2: Send Negotiation Request ---
        print(f"Sending Negotiation to: {negotiation_url}")
        print(f"Payload: {json.dumps(negotiate_payload, indent=2)}\n")

        with httpx.Client() as client:
            response = client.post(negotiation_url, json=negotiate_payload, timeout=5.0)
            response.raise_for_status()  # Check for errors

            response_data = response.json()
            print(f"--- NEGOTIATION RESPONSE RECEIVED (Code: {response.status_code}) ---")
            print(f"{json.dumps(response_data, indent=2)}\n")

            # --- 1.3: Check for Offer and Prepare Commit ---
            if response_data.get("offers"):
                offer = response_data["offers"][0]
                offer_id = offer.get("offerId")
                commit_endpoint = offer.get("commitEndpoint")

                print(f"TEST RESULT: SUCCESS! AS sent offer {offer_id}")
                print(f"Details: {offer.get('price')} {offer.get('currency')}")
                print("Proceding to commit this offer...")

                # --- 1.4: Send Commit Request ---

                # Prepare the payload for the commit endpoint
                commit_payload = {
                    "transactionId": negotiate_payload["transactionId"],  # Must use the same TX ID
                    "offerId": offer_id
                }

                commit_url = f"{BASE_SUPPLIER_URL}{commit_endpoint}"

                print(f"\nSending Commit to: {commit_url}")
                print(f"Payload: {json.dumps(commit_payload, indent=2)}\n")

                commit_response = client.post(commit_url, json=commit_payload, timeout=5.0)
                commit_response.raise_for_status()  # Check for errors

                commit_data = commit_response.json()
                print(f"--- COMMIT RESPONSE RECEIVED (Code: {commit_response.status_code}) ---")
                print(f"{json.dumps(commit_data, indent=2)}\n")

                print("--- v0.3 FULL FLOW COMPLETE ---")
                print(f"STATUS: {commit_data.get('status')}")
                print(f"Confirmation ID: {commit_data.get('confirmationId')}")
                print(f"Message: {commit_data.get('message')}")

            elif response_data.get("rejections"):
                rejection = response_data["rejections"][0]
                print(f"TEST RESULT: REJECTED! AS sent rejection.")
                print(f"Reason: {rejection.get('reasonCode')} - {rejection.get('message')}")

            else:
                print("TEST RESULT: UNKNOWN. No offers or rejections.")

    except httpx.ConnectError:
        print(f"\n--- CLIENT ERROR ---")
        print(f"Connection failed: Could not connect to {BASE_SUPPLIER_URL}.")
        print("Are you sure the 'agent_supplier.py' server is running?")
        sys.exit(1)

    except httpx.HTTPStatusError as e:
        print(f"\n--- CLIENT ERROR ---")
        print(f"HTTP Error: The server responded with a {e.response.status_code} status.")
        print("This might be a 404 (if commit offerId is wrong) or 422 (if payload is wrong).")
        print(f"Response body: {e.response.text}")
        sys.exit(1)

    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR ---")
        print(f"An error occurred: {e}")
        sys.exit(1)

    print("-" * 40 + "\n")


def run_test_2_rejection():
    """
    v0.2: Runs the rejection test case. (No changes for v0.3)
    """
    print("--- RUNNING TEST 2 (EXPECTING REJECTION) ---")

    intent_reject_payload = {
        "transactionId": "uuid-client-AC-005",  # New TX ID
        "requesterId": "urn:ac:my-dev-client:test:003",
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

    negotiation_url = f"{BASE_SUPPLIER_URL}{NEGOTIATE_ENDPOINT}"

    try:
        with httpx.Client() as client:
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

    except httpx.HTTPStatusError as e:
        # This is the expected path for this test
        print(f"HTTP Error: The server responded with a {e.response.status_code} status.")
        print(f"Response body: {e.response.text}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print("-" * 40 + "\n")


def main():
    """
    Main function to run the v0.3 Agent Client tests.
    """
    run_test_1_success_and_commit()
    time.sleep(1)  # Pause for cleaner logs
    run_test_2_rejection()


# --- Run the Script ---
if __name__ == "__main__":
    main()

