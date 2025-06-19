import requests
import uuid
import logging
from config import settings

logger = logging.getLogger(__name__)

class YandexSpeech:
    @staticmethod
    def speech_to_text(audio_data: bytes) -> str:
        try:
            headers = {
                "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
                "x-folder-id": settings.YANDEX_FOLDER_ID
            }
            response = requests.post(
                "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
                headers=headers,
                data=audio_data
            )
            result = response.json()
            return result.get("result", "")
        except Exception as e:
            logger.error(f"Speech recognition error: {str(e)}")
            return ""

    @staticmethod
    def text_to_speech(text: str) -> str:
        try:
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
            response = requests.post(
                "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                headers=headers,
                data=data
            )
            if response.status_code == 200:
                filename = f"tts_{uuid.uuid4()}.ogg"
                with open(filename, "wb") as f:
                    f.write(response.content)
                return filename
        except Exception as e:
            logger.error(f"TTS error: {str(e)}")
            return ""