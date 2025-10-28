# --- Imports ---
import httpx
import sys
import time
import json  # To print JSON payloads nicely
from pydantic import BaseModel
from typing import List, Dict, Optional
import uuid
import asyncio  # v0.7: Import asyncio for concurrent requests

# --- v0.6: Security Configuration ---
# We must match the key defined in 'agent_directory.py'
DIRECTORY_URL = "http://127.0.0.1:8001"
DIRECTORY_API_KEY = "dummy-secret-key-12345"  # The "password" for the directory
API_KEY_NAME = "X-ATP-Directory-Key"  # The "header" name for the key

# --- v0.5: Service Configuration ---
SERVICE_TO_FIND = "booking:flight"


# --- v0.5: Client-side Data Models ---
# These help our client understand the data it receives

class SupplierInfo(BaseModel):
    """
    A minimal representation of a supplier, as discovered
    from the Agent Directory.
    v0.6: Now includes 'isVerified'
    """
    supplierId: str
    name: str
    baseUrl: str
    isVerified: bool  # v0.6: We will check this flag


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


# --- v0.7: Main Client Logic (Asynchronous) ---

async def discover_suppliers(client: httpx.AsyncClient, service_type: str) -> List[SupplierInfo]:
    """
    v0.7: Calls the Agent Directory asynchronously.
    1. Sends the required API Key in the headers.
    2. Filters for 'requireVerified=True' by default.
    """
    print(f"--- 1. DISCOVERY PHASE (v0.7 Async Trust Mode) ---")
    discover_url = f"{DIRECTORY_URL}/discover"

    # v0.6: Define the query parameters
    params = {
        "serviceType": service_type,
        "requireVerified": True  # We only want trusted suppliers
    }

    # v0.6: Define the security headers
    headers = {
        API_KEY_NAME: DIRECTORY_API_KEY
    }

    print(f"Asking Directory ({discover_url}) for service: '{service_type}'")
    print(f"Filtering for verified suppliers only.")
    print(f"Authenticating with API Key...")

    try:
        # v0.7: Use 'await client.get'
        response = await client.get(discover_url, params=params, headers=headers, timeout=5.0)

        # Check for auth failure
        if response.status_code == 403:
            print("\n--- CLIENT ERROR (403 Forbidden) ---")
            print(
                "The Directory rejected our API Key. Check that 'DIRECTORY_API_KEY' matches in both client and directory files.")
            sys.exit(1)

        response.raise_for_status()  # Check for other HTTP errors

        data = response.json()
        suppliers_data = data.get("suppliers", [])

        if not suppliers_data:
            print(f"Discovery FAILED: No verified suppliers found for '{service_type}'")
            return []

        # Parse the suppliers into our model
        found_suppliers = [SupplierInfo(**s) for s in suppliers_data]

        print(f"Discovery SUCCESS: Found {len(found_suppliers)} verified suppliers.")
        for s in found_suppliers:
            print(f"  - {s.name} at {s.baseUrl} (Verified: {s.isVerified})")
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
        print(f"Response body: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\n--- UNEXPECTED ERROR during Discovery ---")
        print(f"An error occurred: {e}")
        sys.exit(1)


async def negotiate_with_single_supplier(client: httpx.AsyncClient, supplier: SupplierInfo, intent_payload: dict) -> \
Optional[Offer]:
    """
    v0.7: Helper function to negotiate with ONE supplier.
    This function is designed to be run concurrently.
    """
    negotiation_url = f"{supplier.baseUrl}/atp/v1/negotiate"

    # Give this negotiation a unique transaction ID
    payload = intent_payload.copy()  # Make a copy to avoid race conditions
    payload["transactionId"] = f"tx-{uuid.uuid4()}"

    try:
        print(f"...Negotiating with {supplier.name} at {negotiation_url}")

        # v0.7: Use 'await client.post'
        response = await client.post(negotiation_url, json=payload, timeout=5.0)
        response.raise_for_status()

        response_data = response.json()

        if response_data.get("offers"):
            offer_data = response_data["offers"][0]
            valid_offer = Offer(
                **offer_data,
                supplier_name=supplier.name,
                supplier_base_url=supplier.baseUrl
            )
            print(f"SUCCESS: {supplier.name} offered {valid_offer.price} {valid_offer.currency}")
            return valid_offer

        elif response_data.get("rejections"):
            rejection_msg = response_data["rejections"][0]["message"]
            print(f"REJECTED: {supplier.name} rejected intent. Reason: {rejection_msg}")
            return None

    except httpx.ConnectError:
        print(f"SKIPPED: Could not connect to {supplier.name} at {supplier.baseUrl}")
    except httpx.HTTPStatusError as e:
        print(f"SKIPPED: {supplier.name} responded with HTTP {e.response.status_code}")
    except Exception as e:
        print(f"SKIPPED: An unexpected error occurred with {supplier.name}: {e}")

    return None


async def negotiate_with_suppliers_concurrently(client: httpx.AsyncClient, suppliers: List[SupplierInfo],
                                                intent_payload: dict) -> List[Offer]:
    """
    v0.7: Main negotiation function.
    Uses asyncio.gather to run all negotiations concurrently.
    """
    print(f"--- 2. NEGOTIATION PHASE (v0.7 Concurrent Mode) ---")
    print(f"Sending intent to {len(suppliers)} verified suppliers *at the same time*...")

    # Create a list of "tasks" to run concurrently
    tasks = [
        negotiate_with_single_supplier(client, supplier, intent_payload)
        for supplier in suppliers
    ]

    # v0.7: Run all tasks concurrently and wait for them to finish
    results = await asyncio.gather(*tasks)

    # Filter out any 'None' results (failures/rejections)
    all_valid_offers = [offer for offer in results if offer is not None]

    print("\n--- Negotiation Phase Complete ---")
    print(f"Collected {len(all_valid_offers)} valid offers.")
    print("-" * 40 + "\n")
    return all_valid_offers


async def select_and_commit_best_offer(client: httpx.AsyncClient, offers: List[Offer], original_tx_id: str):
    """
    v0.7: Updated to be an 'async' function and use 'await client.post'.
    """
    print(f"--- 3. COMMITMENT PHASE ---")

    if not offers:
        print("No valid offers received. Cannot commit.")
        print("TEST FAILED.")
        return

    # --- Selection Logic (No change) ---
    offers.sort(key=lambda o: o.price)
    best_offer = offers[0]

    print(f"Found {len(offers)} offers. Selecting the best one:")
    print(f"  - Winner: {best_offer.supplier_name} with {best_offer.price} {best_offer.currency}")

    # --- Commit Logic ---
    commit_payload = {
        "transactionId": original_tx_id,
        "offerId": best_offer.offerId
    }

    commit_url = f"{best_offer.supplier_base_url}{best_offer.commitEndpoint}"

    try:
        print(f"\nSending Commit to winner: {best_offer.supplier_name} at {commit_url}")
        print(f"Payload: {json.dumps(commit_payload, indent=2)}\n")

        # v0.7: Use 'await client.post'
        commit_response = await client.post(commit_url, json=commit_payload, timeout=5.0)
        commit_response.raise_for_status()

        commit_data = commit_response.json()
        print(f"--- COMMIT RESPONSE RECEIVED (Code: {commit_response.status_code}) ---")
        print(f"{json.dumps(commit_data, indent=2)}\n")

        print(f"--- v0.7 FULL FLOW COMPLETE ---")
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


async def main():
    """
    v0.7: Main function, now asynchronous.
    1. Securely Discover ALL *verified* suppliers.
    2. Negotiate with them *concurrently*.
    3. Select the BEST offer and commit.
    """

    shopping_intent = {
        "transactionId": f"tx-main-{uuid.uuid4()}",
        "requesterId": "urn:ac:my-dev-client:test:007",  # Incremented version
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

    # v0.7: We now use an AsyncClient
    async with httpx.AsyncClient() as client:
        # 1. Discover
        # All functions must be 'awaited'
        suppliers = await discover_suppliers(client, SERVICE_TO_FIND)

        if not suppliers:
            print("Exiting due to discovery failure.")
            sys.exit(1)

        # 2. Negotiate
        # We call our new concurrent function
        all_offers = await negotiate_with_suppliers_concurrently(client, suppliers, shopping_intent)

        # 3. Commit
        await select_and_commit_best_offer(client, all_offers, shopping_intent["transactionId"])


# --- Run the Script ---
if __name__ == "__main__":
    # v0.7: We must use asyncio.run() to start the main async function
    print("--- AGENT CLIENT (AC) v0.7 (Async) STARTED ---")
    start_time = time.time()

    asyncio.run(main())

    end_time = time.time()
    print(f"\n--- Total execution time: {end_time - start_time:.2f} seconds ---")

