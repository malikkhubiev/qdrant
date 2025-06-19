from fastapi import APIRouter, HTTPException
from models.schemas import CallRequest, CallResponse
from services.sipuni import call_with_sipuni
from models.state import CallManager

router = APIRouter()
call_manager = CallManager()

@router.post("/initiate", response_model=CallResponse)
def initiate_call(request: CallRequest):
    call_id = call_manager.create_call()
    try:
        success = call_with_sipuni()
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Не удалось совершить звонок через SIPuni"
            )
        return CallResponse(
            call_id=call_id,
            status="initiated",
            message="Call started to 89054206499"
        )
    except Exception as e:
        call_manager.remove_call(call_id)
        raise