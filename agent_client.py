# --- Imports ---
import httpx
import sys
import time
import json  # To print JSON payloads nicely
from typing import List, Dict, Optional
from pydantic import BaseModel
import uuid


# --- v0.5: Configuration ---
DIRECTORY_URL = "http://127.0.0.1:8001"
SERVICE_TO_FIND = "booking:flight"


# --- v0.5: Client-side Data Models ---
# These help our client understand the data it receives

class SupplierInfo(BaseModel):
    """
    A minimal representation of a supplier, as discovered
    from the Agent Directory.
    """
    supplierId: str
    name: str
    baseUrl: str


class Offer(BaseModel):
    """
    A minimal representation of an offer received from a supplier.
    We add 'supplier_name' and 'supplier_base_url' for our own tracking.
    """
    offerId: str
    price: float
    currency: str
    commitEndpoint: str
    supplier_name: str  # v0.5: Added for tracking
    supplier_base_url: str  # v0.5: Added for tracking


# --- v0.5: Main Client Logic ---

def discover_suppliers(client: httpx.Client, service_type: str) -> List[SupplierInfo]:
    """
    v0.5: Calls the Agent Directory.
    Returns a LIST of suppliers found.
    """
    print(f"--- 1. DISCOVERY PHASE ---")
    discover_url = f"{DIRECTORY_URL}/discover"
    params = {"serviceType": service_type}

    print(f"Asking Directory ({discover_url}) for service: '{service_type}'")

    try:
        response = client.get(discover_url, params=params, timeout=5.0)
        response.raise_for_status()
        data = response.json()

        suppliers_data = data.get("suppliers", [])

        if not suppliers_data:
            print(f"Discovery FAILED: No suppliers found for '{service_type}'")
            return []

        # Parse the suppliers into our model
        found_suppliers = [SupplierInfo(**s) for s in suppliers_data]

        print(f"Discovery SUCCESS: Found {len(found_suppliers)} suppliers.")
        for s in found_suppliers:
            print(f"  - {s.name} at {s.baseUrl}")
        print("-" * 40 + "\n")
        return found_suppliers

    except httpx.ConnectError:
        print(f"\n--- CLIENT ERROR ---")
        print(f"Connection failed: Could not connect to Directory at {DIRECTORY_URL}.")
        print("Are you sure 'agent_directory.py' is running on port 8001?")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\n--- CLIENT ERROR ---")
        print(f"HTTP Error: The Directory responded with a {e.response.status_code} status.")
        sys.exit(1)
    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR during Discovery ---")
        print(f"An error occurred: {e}")
        sys.exit(1)


def negotiate_with_suppliers(client: httpx.Client, suppliers: List[SupplierInfo], intent_payload: dict) -> List[Offer]:
    """
    v0.5: Iterates through all suppliers, sends a negotiation request
    to each, and collects all valid offers.
    """
    print(f"--- 2. NEGOTIATION PHASE ---")
    print(f"Sending intent to {len(suppliers)} suppliers...")

    all_valid_offers: List[Offer] = []

    for supplier in suppliers:
        negotiation_url = f"{supplier.baseUrl}/atp/v1/negotiate"

        # Give each negotiation a unique transaction ID
        intent_payload["transactionId"] = f"tx-{uuid.uuid4()}"

        try:
            print(f"\n...Negotiating with {supplier.name} at {negotiation_url}")

            response = client.post(negotiation_url, json=intent_payload, timeout=5.0)
            response.raise_for_status()

            response_data = response.json()

            if response_data.get("offers"):
                # Supplier made an offer!
                offer_data = response_data["offers"][0]

                # Store the offer with supplier info
                valid_offer = Offer(
                    **offer_data,
                    supplier_name=supplier.name,
                    supplier_base_url=supplier.baseUrl
                )
                all_valid_offers.append(valid_offer)
                print(f"SUCCESS: {supplier.name} offered {valid_offer.price} {valid_offer.currency}")

            elif response_data.get("rejections"):
                # Supplier rejected the intent
                rejection_msg = response_data["rejections"][0]["message"]
                print(f"REJECTED: {supplier.name} rejected intent. Reason: {rejection_msg}")

        except httpx.ConnectError:
            print(f"SKIPPED: Could not connect to {supplier.name} at {supplier.baseUrl}")
            print("Is the 'agent_supplier.py' (or _2.py) running on that port?")
        except httpx.HTTPStatusError as e:
            print(f"SKIPPED: {supplier.name} responded with HTTP {e.response.status_code}")
        except Exception as e:
            print(f"SKIPPED: An unexpected error occurred with {supplier.name}: {e}")

    print("\n--- Negotiation Phase Complete ---")
    print(f"Collected {len(all_valid_offers)} valid offers.")
    print("-" * 40 + "\n")
    return all_valid_offers


def select_and_commit_best_offer(client: httpx.Client, offers: List[Offer], original_tx_id: str):
    """
    v0.5: Selects the best offer (cheapest) and commits to it.
    """
    print(f"--- 3. COMMITMENT PHASE ---")

    if not offers:
        print("No valid offers received. Cannot commit.")
        print("TEST FAILED.")
        return

    # --- Selection Logic ---
    # Sort offers by price, from cheapest to most expensive
    offers.sort(key=lambda o: o.price)
    best_offer = offers[0]

    print(f"Found {len(offers)} offers. Selecting the best one:")
    print(f"  - Winner: {best_offer.supplier_name} with {best_offer.price} {best_offer.currency}")

    # --- Commit Logic ---
    commit_payload = {
        "transactionId": original_tx_id,  # Use a consistent transaction ID
        "offerId": best_offer.offerId
    }

    commit_url = f"{best_offer.supplier_base_url}{best_offer.commitEndpoint}"

    try:
        print(f"\nSending Commit to winner: {best_offer.supplier_name} at {commit_url}")
        print(f"Payload: {json.dumps(commit_payload, indent=2)}\n")

        commit_response = client.post(commit_url, json=commit_payload, timeout=5.0)
        commit_response.raise_for_status()

        commit_data = commit_response.json()
        print(f"--- COMMIT RESPONSE RECEIVED (Code: {commit_response.status_code}) ---")
        print(f"{json.dumps(commit_data, indent=2)}\n")

        print(f"--- v0.5 FULL FLOW COMPLETE ---")
        print(f"STATUS: {commit_data.get('status')}")
        print(f"Confirmation ID: {commit_data.get('confirmationId')}")
        print(f"Message: {commit_data.get('message')}")
        print("\nTEST SUCCEEDED!")

    except httpx.ConnectError:
        print(f"COMMIT FAILED: Could not connect to {best_offer.supplier_name}")
    except httpx.HTTPStatusError as e:
        print(f"COMMIT FAILED: {best_offer.supplier_name} responded with HTTP {e.response.status_code}")
        print(f"Response body: {e.response.text}")

    print("-" * 40 + "\n")


def main():
    """
    Main function to run the v0.5 Agent Client.
    1. Discover ALL suppliers.
    2. Negotiate with ALL of them.
    3. Select the BEST offer and commit.
    """

    # This is the "base" intent for this shopping trip
    # We will send this to all suppliers
    shopping_intent = {
        "transactionId": f"tx-main-{uuid.uuid4()}",  # Base ID
        "requesterId": "urn:ac:my-dev-client:test:005",
        "serviceType": "booking:flight",
        "intent": {
            "params": {
                "from": "CDG",
                "to": "JFK",
                "date": "2025-11-15"
            },
            "constraints": {
                "maxPrice": 500,  # Our budget is 500
                "currency": "EUR"
            }
        }
    }

    with httpx.Client() as client:
        # 1. Discover
        suppliers = discover_suppliers(client, SERVICE_TO_FIND)

        if not suppliers:
            print("Exiting due to discovery failure.")
            sys.exit(1)

        # 2. Negotiate
        all_offers = negotiate_with_suppliers(client, suppliers, shopping_intent)

        # 3. Commit
        select_and_commit_best_offer(client, all_offers, shopping_intent["transactionId"])


# --- Run the Script ---
if __name__ == "__main__":
    import uuid

    main()

