from pydantic import BaseModel
from typing import Optional

class CallRequest(BaseModel):
    phone_number: str
    caller_id: Optional[str] = "AI Assistant"

class CallResponse(BaseModel):
    call_id: str
    status: str
    message: Optional[str] = None

class VoiceResponse(BaseModel):
    call_id: str
    text: str