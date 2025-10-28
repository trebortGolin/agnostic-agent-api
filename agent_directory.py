# --- Imports ---
from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional

# --- Application Initialization ---
app = FastAPI(
    title="Agent Directory (AD) ATP Prototype",
    description="v0.6 implementation: The 'Discovery' layer with a Trust/Security layer.",
    version="0.6",
)

# --- v0.6: Security Configuration ---
# This is our "master key" for the directory.
# In a real app, this would be in a secure .env file
API_KEY_NAME = "X-ATP-Directory-Key"
DIRECTORY_API_KEY = "dummy-secret-key-12345"  # This is the key our client must present

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)


async def get_api_key(api_key: str = Security(api_key_header)):
    """
    Dependency function to validate the API key.
    """
    if api_key == DIRECTORY_API_KEY:
        return api_key
    else:
        print(f"--- FAILED AUTH ATTEMPT ---")
        print(f"Invalid API Key received: {api_key}")
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API Key"
        )


# --- Schema Definitions for Discovery ---

class SupplierInfo(BaseModel):
    """
    v0.6: The structured information about a single supplier (AS)
    We added the 'isVerified' flag.
    """
    supplierId: str
    name: str
    baseUrl: str  # The root URL for the supplier's ATP endpoints
    supportedServices: List[str]
    isVerified: bool = False  # v0.6: The "Trust Badge"


class DiscoveryResponse(BaseModel):
    """
    The response from the discovery endpoint.
    """
    serviceType: str
    suppliers: List[SupplierInfo]


# --- In-Memory "Database" of Registered Suppliers ---
# v0.6 Update: We now include the 'isVerified' flag
REGISTERED_SUPPLIERS = {
    "urn:as:flight-supplier-demo:001": SupplierInfo(
        supplierId="urn:as:flight-supplier-demo:001",
        name="Demo Flight Supplier (AS)",
        baseUrl="http://127.0.0.1:8000",
        supportedServices=["booking:flight", "booking:hotel"],
        isVerified=True  # This is a trusted supplier
    ),
    "urn:as:weather-supplier-demo:002": SupplierInfo(
        supplierId="urn:as:weather-supplier-demo:002",
        name="Demo Weather Supplier",
        baseUrl="http://127.0.0.1:8002",
        supportedServices=["weather:forecast"],
        isVerified=True
    ),
    "urn:as:airdemo-competitor:003": SupplierInfo(
        supplierId="urn:as:airdemo-competitor:003",
        name="AirDemo (Competitor)",
        baseUrl="http://127.0.0.1:8003",
        supportedServices=["booking:flight"],
        isVerified=True
    ),
    # --- v0.6: Add an "untrusted" supplier for testing ---
    "urn:as:unverified-flyer:004": SupplierInfo(
        supplierId="urn:as:unverified-flyer:004",
        name="FlyByNight Airways (Unverified)",
        baseUrl="http://127.0.0.1:8004",  # We won't run this server
        supportedServices=["booking:flight"],
        isVerified=False  # This is an untrusted supplier
    ),
    # ----------------------------------------------------
}


# --- Endpoint 1: Discovery (/discover) ---

@app.get("/discover", response_model=DiscoveryResponse)
async def discover_suppliers(
        # v0.6: Add a new filter parameter
        service_type: str = Query(..., alias="serviceType",
                                  description="The type of service the client is looking for"),
        min_trust: bool = Query(True, alias="requireVerified",
                                description="Client filters for verified suppliers only"),
        # v0.6: Add our API Key dependency to secure this endpoint
        api_key: str = Depends(get_api_key)
):
    """
    v0.6: The discovery endpoint.
    1. Requires a valid API key to use.
    2. Allows client to filter for verified suppliers.
    """
    print(f"\n--- NEW DISCOVERY REQUEST RECEIVED ---")
    print(f"Client is looking for service: {service_type}")
    print(f"Client requires verification: {min_trust}")

    # Find all suppliers that support this service type
    found_suppliers = []
    for supplier in REGISTERED_SUPPLIERS.values():
        if service_type in supplier.supportedServices:
            # v0.6: Apply the trust filter
            if min_trust and not supplier.isVerified:
                print(f"Skipping unverified supplier: {supplier.name}")
                continue  # Skip this one

            found_suppliers.append(supplier)

    if not found_suppliers:
        print(f"No suppliers found matching criteria.")
        raise HTTPException(
            status_code=404,
            detail=f"No suppliers found matching criteria for service: {service_type}"
        )

    print(f"Found {len(found_suppliers)} supplier(s). Responding.")

    response = DiscoveryResponse(
        serviceType=service_type,
        suppliers=found_suppliers
    )

    return response


# --- Run the Server (When executing this file directly) ---
if __name__ == "__main__":
    import uvicorn

    # We run this on port 8001
    DIRECTORY_PORT = 8001
    print(f"Starting Agent Directory (AD) server v0.6 on http://127.0.0.1:{DIRECTORY_PORT}")
    print(f"This server requires an API Key: {DIRECTORY_API_KEY}")

    uvicorn.run("agent_directory:app", host="127.0.0.1", port=DIRECTORY_PORT, reload=True)

