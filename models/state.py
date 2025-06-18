import time
import uuid
from typing import Dict, Optional

class CallState:
    def __init__(self):
        self.dialog_history: list = []
        self.last_activity: float = time.time()
        self.recognition_active: bool = False
        self.audio_buffer: bytes = b""
        self.current_question: str = ""
        self.waiting_for_response: bool = False
        self.call_id: Optional[str] = None

class CallManager:
    def __init__(self):
        self.active_calls: Dict[str, CallState] = {}
    
    def create_call(self, call_id: str = None) -> str:
        call_id = call_id or str(uuid.uuid4())
        self.active_calls[call_id] = CallState()
        self.active_calls[call_id].call_id = call_id
        return call_id
    
    def remove_call(self, call_id: str):
        if call_id in self.active_calls:
            del self.active_calls[call_id]