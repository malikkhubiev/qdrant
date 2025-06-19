import requests
import hashlib
import os
import logging
from config import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)

SIPUNI_USER = os.environ.get("SIPUNI_USER", "")
SIPUNI_SIPNUMBER = os.environ.get("SIPUNI_SIPNUMBER", "")
SIPUNI_SECRET = os.environ.get("SIPUNI_SECRET", "")
SIPUNI_API_URL = "https://sipuni.com/api/voicecall/call"

FIXED_PHONE = "89054206499"
FIXED_MESSAGE = "Здравствуйте! Я готов ответить на ваши вопросы. Говорите после сигнала."
FIXED_VOICE = "Anna_n"

def generate_sipuni_hash(message: str, phone: str, voice: str) -> str:
    hash_string = "+".join([message, phone, SIPUNI_SIPNUMBER, SIPUNI_USER, voice, SIPUNI_SECRET])
    return hashlib.md5(hash_string.encode()).hexdigest()

def call_with_sipuni():
    phone = FIXED_PHONE
    message = FIXED_MESSAGE
    voice = FIXED_VOICE
    hash_value = generate_sipuni_hash(message, phone, voice)
    payload = {
        "user": SIPUNI_USER,
        "phone": phone,
        "message": message,
        "voice": voice,
        "sipnumber": SIPUNI_SIPNUMBER,
        "hash": hash_value,
    }
    logger.info(f"SIPuni voicecall payload: {payload}")
    response = requests.post(SIPUNI_API_URL, data=payload)
    logger.info(f"SIPuni response status: {response.status_code}")
    logger.info(f"SIPuni response text: {response.text}")
    return response.status_code == 200

class SIPuniService:
    @staticmethod
    def make_request(endpoint: str, payload: dict):
        url = f"https://sipuni.com/api{endpoint}"
        payload['secret'] = settings.SIPUNI_API_KEY
        logger.info(f"SIPuni request URL: {url}")
        logger.info(f"SIPuni request payload: {payload}")
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=30
            )
            logger.info(f"SIPuni response status: {response.status_code}")
            logger.info(f"SIPuni response text: {response.text}")
            if response.status_code != 200:
                error = response.text
                logger.error(f"SIPuni error: {error}")
                raise HTTPException(
                    status_code=502,
                    detail=f"SIPuni API error: {error}"
                )
            try:
                return response.json()
            except Exception as e:
                logger.error(f"SIPuni response not JSON: {response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"SIPuni returned non-JSON: {response.text}"
                )
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