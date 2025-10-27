# --- Imports ---
# 1. Import FastAPI to create our web application
# 2. Import BaseModel from Pydantic to define our JSON "schemas"
# 3. Import List from 'typing' to define data types (Removed Optional)
from fastapi import FastAPI
from pydantic import BaseModel  # Removed Field
from typing import List

# --- Application Initialization ---
# Creates the "brain" of our agent supplier
app = FastAPI(
    title="Agent Supplier (AS) ATP Prototype",
    description="v0.1 implementation of the ATP specification",
    version="0.1",
)


# --- Data Schema Definitions (The "Grammar" of ATP) ---
# These Python classes FORCE the JSON structure.
# If an Agent Client sends JSON that doesn't match, FastAPI will reject it.
# This is our protocol validation, implemented automatically.

# Note: For v0.1, we are keeping the 'intent' field as a flexible 'dict'
# to match the client's simple structure.
# In v0.2, we would define these nested Pydantic models.
#
# from pydantic import Field
# from typing import Optional
#
# class IntentParams(BaseModel):
#     from_city: str = Field(..., alias="from", description="IATA code (e.g., CDG)")
#     to_city: str = Field(..., alias="to", description="IATA code (e.g., JFK)")
#     date: str = Field(..., description="Date in YYYY-MM-DD format")
#
# class IntentConstraints(BaseModel):
#     maxPrice: Optional[int] = None
#     currency: Optional[str] = None
#     maxStops: Optional[int] = None

# Main Schema for the REQUEST: IntentRequest
class IntentRequest(BaseModel):
    transactionId: str
    requesterId: str
    serviceType: str
    # For v0.1, we keep 'intent' as a simple dictionary for flexibility.
    intent: dict


# Schema for the 'details' of the offer
class OfferDetails(BaseModel):
    flight: str
    departureTime: str
    arrivalTime: str


# Main Schema for the RESPONSE: OfferResponse
class OfferResponse(BaseModel):
    transactionId: str
    negotiationId: str
    offers: List[dict]  # A list of dictionaries (for v0.1)
    rejections: List[dict]


# --- The API Endpoint (The Agent's "Front Door") ---

# '@app.post(...)' is a "decorator":
# It tells FastAPI: "When an HTTP POST request comes to '/atp/v1/negotiate',
# execute the 'negotiate_transaction' function below."
@app.post("/atp/v1/negotiate", response_model=OfferResponse)
async def negotiate_transaction(request: IntentRequest):
    """
    This is the main ATP entry point (Phase 2).
    It receives an 'IntentRequest' and MUST return an 'OfferResponse'.
    """

    print("--- NEW ATP REQUEST RECEIVED ---")
    print(f"Requester ID: {request.requesterId}")
    print(f"Transaction ID: {request.transactionId}")
    print(f"Service requested: {request.serviceType}")
    print(f"Intent: {request.intent}")

    # --- Business Logic (Static for this prototype) ---
    # Here, a real AF would read the constraints (e.g., request.intent['constraints'])
    # and query its real flight database.

    # For our prototype, we always return the same offer.

    # 1. Create the static offer (based on the White Paper)
    static_offer = {
        "offerId": "offer-af-001",
        "serviceType": "booking:flight",
        "details": {
            "flight": "AF006",
            "departureTime": "2025-11-15T18:30:00Z",
            "arrivalTime": "2025-11-15T21:00:00Z"
        },
        "price": 480,
        "currency": "EUR",
        "expiresAt": "2025-10-28T12:30:00Z",  # Put a future date/time
        "commitEndpoint": "https://api.af.com/atp/v1/commit"  # Dummy
    }

    # 2. Build the final response
    response_data = {
        "transactionId": request.transactionId,  # We echo the client's ID
        "negotiationId": "uuid-supplier-9876-AS",  # Our internal tracking ID
        "offers": [static_offer],  # We place our offer in the list
        "rejections": []
    }

    print("--- ATP RESPONSE SENT ---")
    print(response_data)

    # 3. Return the response.
    # FastAPI will validate it (thanks to 'response_model=OfferResponse')
    # and convert it to JSON to send to the client.
    return response_data


# --- Run the Server (When executing this file directly) ---
if __name__ == "__main__":
    import uvicorn

    print("Starting Agent Supplier (AS) server on http://127.0.0.1:8000")
    # 'app' : the FastAPI object
    # 'host' : "127.0.0.1" (localhost, your machine)
    # 'port' : 8000 (the "door" we are listening on)
    # 'reload' : True (the server restarts if we change the code, very useful)

    # --- FIX ---
    # Renamed "Agent_supplier:app" to "agent_supplier:app" to match
    # standard Python module naming (lowercase).
    uvicorn.run("agent_supplier:app", host="127.0.0.1", port=8000, reload=True)
