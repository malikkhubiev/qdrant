import aiohttp
import uuid
import logging
from config import settings

logger = logging.getLogger(__name__)

class YandexSpeech:
    @staticmethod
    async def speech_to_text(audio_data: bytes) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
                    "x-folder-id": settings.YANDEX_FOLDER_ID
                }
                
                async with session.post(
                    "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
                    headers=headers,
                    data=audio_data
                ) as response:
                    result = await response.json()
                    return result.get("result", "")
        except Exception as e:
            logger.error(f"Speech recognition error: {str(e)}")
            return ""

    @staticmethod
    async def text_to_speech(text: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
                    "x-folder-id": settings.YANDEX_FOLDER_ID
                }
                
                data = {
                    "text": text,
                    "lang": "ru-RU",
                    "voice": "alena",
                    "format": "oggopus"
                }
                
                async with session.post(
                    "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                    headers=headers,
                    data=data
                ) as response:
                    if response.status == 200:
                        filename = f"tts_{uuid.uuid4()}.ogg"
                        with open(filename, "wb") as f:
                            f.write(await response.read())
                        return filename
        except Exception as e:
            logger.error(f"TTS error: {str(e)}")
            return ""