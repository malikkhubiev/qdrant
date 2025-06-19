import requests
import logging
from config import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class SIPuniService:
    @staticmethod
    def make_request(endpoint: str, payload: dict):
        url = f"https://sipuni.com/api{endpoint}"
        payload['secret'] = settings.SIPUNI_API_KEY
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=30
            )
            if response.status_code != 200:
                error = response.text
                logger.error(f"SIPuni error: {error}")
                raise HTTPException(
                    status_code=502,
                    detail=f"SIPuni API error: {error}"
                )
            return response.json()
        except Exception as e:
            logger.error(f"SIPuni request failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"SIPuni request failed: {str(e)}"
            )
    
    @classmethod
    def initiate_call(cls, phone: str, call_id: str):
        return cls.make_request(
            "/callback/call_number",
            {
                "phone": phone,
                "sipnumber": settings.SIPUNI_SIP_ID,
                "callerid": "AI Assistant",
                "webhook": f"{settings.BASE_URL}/api/events",
                "custom_data": call_id
            }
        )
    
    @classmethod
    def play_audio(cls, call_id: str, audio_url: str):
        return cls.make_request(
            "/callback/play",
            {
                "call_id": call_id,
                "audio_url": audio_url,
                "silence_detect": True
            }
        )