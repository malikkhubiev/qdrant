from dataclasses import dataclass
from typing import Optional

@dataclass
class CallRequest:
    phone_number: str
    caller_id: Optional[str] = "AI Assistant"

@dataclass
class CallResponse:
    call_id: str
    status: str
    message: Optional[str] = None

@dataclass
class VoiceResponse:
    call_id: str
    text: str