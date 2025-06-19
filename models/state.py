import time
import uuid

class CallState:
    def __init__(self):
        self.dialog_history = []
        self.last_activity = time.time()
        self.recognition_active = False
        self.audio_buffer = b""
        self.current_question = ""
        self.waiting_for_response = False
        self.call_id = None

class CallManager:
    def __init__(self):
        self.active_calls = {}
    
    def create_call(self, call_id=None) -> str:
        call_id = call_id or str(uuid.uuid4())
        self.active_calls[call_id] = CallState()
        self.active_calls[call_id].call_id = call_id
        return call_id
    
    def remove_call(self, call_id: str):
        if call_id in self.active_calls:
            del self.active_calls[call_id]