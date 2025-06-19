from fastapi import APIRouter, HTTPException
from models.schemas import CallRequest, CallResponse
from services.sipuni import SIPuniService
from models.state import CallManager

router = APIRouter()
call_manager = CallManager()

@router.post("/initiate", response_model=CallResponse)
def initiate_call(request: CallRequest):
    call_id = call_manager.create_call()
    try:
        result = SIPuniService.initiate_call(
            phone=request.phone_number,
            call_id=call_id
        )
        if result.get("result") != "success":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Call failed")
            )
        return CallResponse(
            call_id=call_id,
            status="initiated",
            message="Call started"
        )
    except Exception as e:
        call_manager.remove_call(call_id)
        raise