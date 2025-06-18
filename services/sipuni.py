import aiohttp
import logging
from fastapi import HTTPException
from config import settings

logger = logging.getLogger(__name__)

class SIPuniService:
    @staticmethod
    async def make_request(endpoint: str, payload: dict):
        url = f"https://sipuni.com/api{endpoint}"
        payload['secret'] = settings.SIPUNI_API_KEY
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        logger.error(f"SIPuni error: {error}")
                        raise HTTPException(
                            status_code=502,
                            detail=f"SIPuni API error: {error}"
                        )
                    return await response.json()
        except Exception as e:
            logger.error(f"SIPuni request failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"SIPuni request failed: {str(e)}"
            )
    
    @classmethod
    async def initiate_call(cls, phone: str, call_id: str):
        return await cls.make_request(
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
    async def play_audio(cls, call_id: str, audio_url: str):
        return await cls.make_request(
            "/callback/play",
            {
                "call_id": call_id,
                "audio_url": audio_url,
                "silence_detect": True
            }
        )