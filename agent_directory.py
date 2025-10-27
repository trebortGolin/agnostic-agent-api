# --- Imports ---
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List

# --- Application Initialization ---
app = FastAPI(
    title="Agent Directory (AD) ATP Prototype",
    description="v0.4 implementation: The 'Discovery' layer.",
    version="0.4",
)


# --- Schema Definitions for Discovery ---

class SupplierInfo(BaseModel):
    """
    The structured information about a single supplier (AS)
    """
    supplierId: str
    name: str
    baseUrl: str  # The root URL for the supplier's ATP endpoints
    supportedServices: List[str]


class DiscoveryResponse(BaseModel):
    """
    The response from the discovery endpoint, containing
    a list of suppliers that match the query.
    """
    serviceType: str
    suppliers: List[SupplierInfo]


# --- In-Memory "Database" of Registered Suppliers ---
# This is our core commercial asset.
# In a real app, this would be a massive, scalable database.
REGISTERED_SUPPLIERS = {
    "urn:as:flight-supplier-demo:001": SupplierInfo(
        supplierId="urn:as:flight-supplier-demo:001",
        name="Demo Flight Supplier (AS)",
        baseUrl="http://127.0.0.1:8000",
        supportedServices=["booking:flight", "booking:hotel"]
    ),
    "urn:as:weather-supplier-demo:002": SupplierInfo(
        supplierId="urn:as:weather-supplier-demo:002",
        name="Demo Weather Supplier",
        baseUrl="http://127.0.0.1:8002",  # Note: a different server
        supportedServices=["weather:forecast"]
    ),
}


# --- Endpoint 1: Discovery (/discover) ---

@app.get("/discover", response_model=DiscoveryResponse)
async def discover_suppliers(
        service_type: str = Query(..., alias="serviceType", description="The type of service the client is looking for")
):
    """
    v0.4: The main discovery endpoint.
    Clients query this to find suppliers for a specific service.
    """
    print(f"\n--- NEW DISCOVERY REQUEST RECEIVED ---")
    print(f"Client is looking for service: {service_type}")

    # Find all suppliers that support this service type
    found_suppliers = []
    for supplier in REGISTERED_SUPPLIERS.values():
        if service_type in supplier.supportedServices:
            found_suppliers.append(supplier)

    if not found_suppliers:
        print(f"No suppliers found for: {service_type}")
        raise HTTPException(
            status_code=404,
            detail=f"No suppliers found supporting service type: {service_type}"
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

    # We run this on a *different port* (8001) than our supplier (8000)
    DIRECTORY_PORT = 8001
    print(f"Starting Agent Directory (AD) server v0.4 on http://127.0.0.1:{DIRECTORY_PORT}")

    uvicorn.run("agent_directory:app", host="127.0.0.1", port=DIRECTORY_PORT, reload=True)
