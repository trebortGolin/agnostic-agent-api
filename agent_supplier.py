# --- Imports ---
# v0.3: We need 'HTTPException' to return errors (like 404)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Application Initialization ---
app = FastAPI(
    title="Agent Supplier (AS) ATP Prototype",
    description="v0.3 implementation: Added /commit endpoint",
    version="0.3",
)


# --- v0.2: Strict Schema Definitions (Negotiation Phase) ---

class IntentParams(BaseModel):
    from_city: str = Field(..., alias="from", description="IATA code (e.g., CDG)")
    to_city: str = Field(..., alias="to", description="IATA code (e.g., JFK)")
    date: str = Field(..., description="Date in YYYY-MM-DD format")


class IntentConstraints(BaseModel):
    maxPrice: Optional[int] = None
    currency: Optional[str] = None


class Intent(BaseModel):
    params: IntentParams
    constraints: IntentConstraints


class IntentRequest(BaseModel):
    transactionId: str
    requesterId: str
    serviceType: str
    intent: Intent


class OfferDetails(BaseModel):
    flight: str
    departureTime: str
    arrivalTime: str


class Offer(BaseModel):
    offerId: str
    serviceType: str
    details: OfferDetails
    price: int
    currency: str
    expiresAt: str
    commitEndpoint: str  # The client *must* use this endpoint


class Rejection(BaseModel):
    reasonCode: str
    message: str


class OfferResponse(BaseModel):
    transactionId: str
    negotiationId: str
    offers: List[Offer]
    rejections: List[Rejection]


# --- v0.3: NEW Strict Schema Definitions (Commit Phase) ---

# This is the schema for the REQUEST to the /commit endpoint
class CommitRequest(BaseModel):
    transactionId: str  # Must match the original transactionId
    offerId: str  # The specific offerId the client accepts


# This is the schema for the RESPONSE from the /commit endpoint
class CommitResponse(BaseModel):
    transactionId: str
    commitId: str
    status: str
    confirmationId: str
    message: str


# --- In-Memory "Database" (for demo purposes) ---
# We need to "remember" the offer we made so we can validate the commit
# In a real app, this would be a Redis cache or a database.
# key: offerId, value: Offer object
db_valid_offers = {}


# --- Endpoint 1: Negotiation (/atp/v1/negotiate) ---

@app.post("/atp/v1/negotiate", response_model=OfferResponse)
async def negotiate_transaction(request: IntentRequest):
    """
    v0.2 Logic: Validates intent and dynamically responds.
    v0.3 Update: Now saves the valid offer to our 'database'.
    """

    print("\n--- NEW ATP v0.2 NEGOTIATION RECEIVED ---")
    print(f"Transaction ID: {request.transactionId}")
    print(f"Intent Constraints: {request.intent.constraints}")

    client_max_price = request.intent.constraints.maxPrice
    OUR_PRICE = 480
    OUR_OFFER_ID = f"offer-af-{request.transactionId}"  # Make offerId unique

    if client_max_price is not None and client_max_price < OUR_PRICE:
        # Client's budget is too low. Reject.
        print(f"Client maxPrice ({client_max_price}) is too low. Rejecting.")
        rejection = Rejection(
            reasonCode="PRICE_UNMET",
            message=f"Offered price ({OUR_PRICE}) exceeds client's maxPrice constraint ({client_max_price})."
        )
        response = OfferResponse(
            transactionId=request.transactionId,
            negotiationId=f"uuid-supplier-v0.3-reject",
            offers=[],
            rejections=[rejection]
        )

    else:
        # Client's budget is fine. Make the offer.
        print(f"Client constraints met. Sending offer: {OUR_OFFER_ID}")

        static_offer = Offer(
            offerId=OUR_OFFER_ID,  # Use the unique offer ID
            serviceType="booking:flight",
            details=OfferDetails(
                flight="AF006",
                departureTime="2025-11-15T18:30:00Z",
                arrivalTime="2025-11-15T21:00:00Z"
            ),
            price=OUR_PRICE,
            currency="EUR",
            expiresAt="2025-11-15T12:30:00Z",
            # v0.3: Tell the client *exactly* which endpoint to call to commit
            commitEndpoint="/atp/v1/commit"
        )

        # v0.3: Save this valid offer to our "database" so we can check it later
        db_valid_offers[OUR_OFFER_ID] = static_offer

        response = OfferResponse(
            transactionId=request.transactionId,
            negotiationId=f"uuid-supplier-v0.3-offer",
            offers=[static_offer],
            rejections=[]
        )

    print("--- ATP v0.2 NEGOTIATION RESPONSE SENT ---")
    return response


# --- v0.3: NEW Endpoint 2: Commit (/atp/v1/commit) ---

@app.post("/atp/v1/commit", response_model=CommitResponse)
async def commit_transaction(request: CommitRequest):
    """
    v0.3: This endpoint receives the client's acceptance of an offer.
    It validates the offerId and confirms the "booking".
    """

    print("\n--- NEW ATP v0.3 COMMIT RECEIVED ---")
    print(f"Transaction ID: {request.transactionId}")
    print(f"Attempting to commit Offer ID: {request.offerId}")

    # --- v0.3: Validation Logic ---
    # Check if the offerId from the client is one we actually made
    if request.offerId not in db_valid_offers:
        print(f"COMMIT FAILED: Offer ID '{request.offerId}' not found in database.")
        # If not, raise an HTTP 404 (Not Found) error
        raise HTTPException(
            status_code=404,
            detail=f"Offer ID '{request.offerId}' not found or expired."
        )

    # If we are here, the offer is valid!
    # In a real app, we would now charge the credit card, book the seat, etc.

    # We can safely remove the offer from the DB so it can't be used again
    offer_details = db_valid_offers.pop(request.offerId)

    print(f"COMMIT SUCCESS: Offer {request.offerId} (Flight {offer_details.details.flight}) confirmed.")

    # Create a final confirmation ID
    confirmation_code = f"CONF-{request.transactionId.split('-')[-1]}"

    # Send the final successful response
    response = CommitResponse(
        transactionId=request.transactionId,
        commitId=f"commit-{request.offerId}",
        status="CONFIRMED",
        confirmationId=confirmation_code,
        message="Your flight is confirmed."
    )

    print("--- ATP v0.3 COMMIT RESPONSE SENT ---")
    return response


# --- Run the Server (When executing this file directly) ---
if __name__ == "__main__":
    import uvicorn

    print("Starting Agent Supplier (AS) server v0.3 on http://127.0.0.1:8000")

    # We must use the lowercase filename "agent_supplier" here
    uvicorn.run("agent_supplier:app", host="127.0.0.1", port=8000, reload=True)

