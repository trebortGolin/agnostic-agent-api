# --- Imports ---
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import uvicorn
import uuid  # For generating unique IDs

# --- v0.5: Configuration for our *second* supplier ---
# This is our competitor. It's cheaper!
OUR_PRICE = 475.00
OUR_CURRENCY = "EUR"
OUR_NAME = "AirDemo (Competitor)"
OUR_PORT = 8003  # Must run on a different port

# --- Application Initialization ---
app = FastAPI(
    title=f"Agent Supplier (AS) - {OUR_NAME}",
    description="v0.5 implementation: A *competing* supplier.",
    version="0.5",
)

# --- "Database" ---
# This in-memory dictionary simulates a database of offers
# that this specific supplier has made.
db_valid_offers: Dict[str, 'Offer'] = {}


# --- Schemas (Copied from v0.3) ---

class IntentParams(BaseModel):
    """
    The specific parameters of what the client wants.
    We are strict about 'from' and 'to' being IATA codes.
    """
    origin: str = Field(..., alias="from")
    destination: str = Field(..., alias="to")
    date: str


class IntentConstraints(BaseModel):
    """
    The client's constraints (e.g., budget).
    """
    maxPrice: Optional[float] = None
    currency: Optional[str] = None


class Intent(BaseModel):
    """
    A full, validated Intent object.
    """
    params: IntentParams
    constraints: IntentConstraints


class IntentRequest(BaseModel):
    """
    The complete request payload for the /negotiate endpoint.
    """
    transactionId: str
    requesterId: str
    serviceType: str
    intent: Intent


class Offer(BaseModel):
    """
    A single, binding offer from the supplier.
    """
    offerId: str
    price: float
    currency: str
    commitEndpoint: str  # The endpoint the client must call to accept


class Rejection(BaseModel):
    """
    A formal rejection of the client's intent.
    """
    reasonCode: str
    message: str


class NegotiateResponse(BaseModel):
    """
    The response from the /negotiate endpoint.
    It *must* contain either offers or rejections.
    """
    transactionId: str
    negotiationId: str
    offers: List[Offer] = []
    rejections: List[Rejection] = []


class CommitRequest(BaseModel):
    """
    The request payload for the /commit endpoint.
    """
    transactionId: str
    offerId: str


class CommitResponse(BaseModel):
    """
    The final confirmation payload from the /commit endpoint.
    """
    transactionId: str
    offerId: str
    status: str
    confirmationId: str
    message: str


# --- Endpoint 1: Negotiation (/negotiate) ---

@app.post("/atp/v1/negotiate", response_model=NegotiateResponse)
async def negotiate(request: IntentRequest = Body(...)):
    """
    v0.5: The negotiation endpoint for the *competitor*.
    """
    print(f"\n--- [{OUR_NAME} @ Port {OUR_PORT}] NEW ATP REQUEST RECEIVED ---")
    print(f"Transaction ID: {request.transactionId}")
    print(f"Service requested: {request.serviceType}")

    negotiation_id = f"uuid-supplier-B-{uuid.uuid4()}"

    # --- Dynamic Logic ---
    # Check if the client's budget (maxPrice) is high enough
    client_max_price = request.intent.constraints.maxPrice

    offers_list = []
    rejections_list = []

    # Check if a budget was specified
    if client_max_price is not None:
        if client_max_price >= OUR_PRICE:
            # Client's budget is acceptable. Create an offer.
            offer_id = f"offer-B-{uuid.uuid4()}"
            new_offer = Offer(
                offerId=offer_id,
                price=OUR_PRICE,
                currency=OUR_CURRENCY,
                commitEndpoint="/atp/v1/commit"  # This supplier's commit endpoint
            )
            offers_list.append(new_offer)

            # "Save" this valid offer to our temporary DB
            db_valid_offers[offer_id] = new_offer

            print(f"Client budget ({client_max_price}) > Our price ({OUR_PRICE}). Making offer {offer_id}.")

        else:
            # Client's budget is too low. Create a rejection.
            rejection = Rejection(
                reasonCode="BUDGET_TOO_LOW",
                message=f"Max price {client_max_price} is below our minimum of {OUR_PRICE}"
            )
            rejections_list.append(rejection)
            print(f"Client budget ({client_max_price}) < Our price ({OUR_PRICE}). Rejecting.")
    else:
        # No budget specified, just send the offer
        offer_id = f"offer-B-{uuid.uuid4()}"
        new_offer = Offer(
            offerId=offer_id,
            price=OUR_PRICE,
            currency=OUR_CURRENCY,
            commitEndpoint="/atp/v1/commit"
        )
        offers_list.append(new_offer)
        db_valid_offers[offer_id] = new_offer
        print(f"No client budget. Making offer {offer_id}.")

    # Create and send the final response
    response = NegotiateResponse(
        transactionId=request.transactionId,
        negotiationId=negotiation_id,
        offers=offers_list,
        rejections=rejections_list
    )

    print(f"--- [{OUR_NAME}] ATP RESPONSE SENT ---")
    return response


# --- Endpoint 2: Commit (/commit) ---

@app.post("/atp/v1/commit", response_model=CommitResponse)
async def commit(request: CommitRequest = Body(...)):
    """
    v0.5: The commit endpoint for the *competitor*.
    """
    print(f"\n--- [{OUR_NAME} @ Port {OUR_PORT}] NEW COMMIT REQUEST RECEIVED ---")
    print(f"Transaction ID: {request.transactionId}")
    print(f"Attempting to commit offerId: {request.offerId}")

    # Check if the offerId is one we actually made
    if request.offerId in db_valid_offers:
        # Success!
        print(f"Offer {request.offerId} found and confirmed.")

        # Remove offer from DB so it can't be used again
        db_valid_offers.pop(request.offerId)

        confirmation_id = f"conf-B-{uuid.uuid4()}"
        response = CommitResponse(
            transactionId=request.transactionId,
            offerId=request.offerId,
            status="CONFIRMED",
            confirmationId=confirmation_id,
            message=f"Booking confirmed via {OUR_NAME}."
        )
        return response
    else:
        # Failure!
        print(f"Error: Offer {request.offerId} not found or already used.")
        raise HTTPException(
            status_code=404,
            detail=f"Offer ID {request.offerId} not found or has expired."
        )


# --- Run the Server ---
if __name__ == "__main__":
    print(f"Starting Agent Supplier (AS) server [{OUR_NAME}] on http://127.0.0.1:{OUR_PORT}")

    # Note: We run on OUR_PORT (8003)
    uvicorn.run("agent_supplier_2:app", host="127.0.0.1", port=OUR_PORT, reload=True)
