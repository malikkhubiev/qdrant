from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import JSONResponse
from models.state import CallManager
from services.yandex import YandexSpeech
from services.deepseek import DeepSeekAI
from services.sipuni import SIPuniService
import logging
from config import *
import requests

router = APIRouter()
call_manager = CallManager()
logger = logging.getLogger(__name__)

FIXED_RESPONSE = [
    {
        "id": 5,
        "text": "Цена: Виртуальный хостинг — 300 руб./месяц",
        "tags": "цены",
        "score": 0.7761
    },
    {
        "id": 7,
        "text": "Акция: Бесплатный домен при оплате года хостинга",
        "tags": "акции",
        "score": 0.7239
    },
    {
        "id": 49,
        "text": "Гарантия: Бесплатный хостинг при разработке сайта",
        "tags": "гарантии",
        "score": 0.655
    }
]

@router.post("/sipuni")
def handle_sipuni_event(request: Request):
    data = request.json()
    call_id = data.get("custom_data")
    
    if not call_id:
        return JSONResponse({"status": "error"}, status_code=400)
    
    if data.get("status") == "answered":
        # Приветствие клиента
        greeting = "Здравствуйте! Вас приветствует робот-менеджер по продажам. Чем могу помочь?"
        audio_file = YandexSpeech.text_to_speech(greeting)
        SIPuniService.play_audio(call_id, f"{settings.BASE_URL}/audio/{audio_file}")
        return JSONResponse({"status": "greeted"})
    elif data.get("record_url"):
        process_audio(call_id, data["record_url"])
    
    return JSONResponse({"status": "processed"})

def process_audio(call_id: str, audio_url: str):
    resp = requests.get(audio_url)
    audio_data = resp.content
    text = YandexSpeech.speech_to_text(audio_data)
    # Упрощение запроса через DeepSeek (можно использовать тот же prompt)
    # simplified = DeepSeekAI.generate_response(f"Упрости и переформулируй для поиска: {text}")
    # generate_and_play_response(call_id, simplified)
    # Мокаем DeepSeek и генерацию ответа:
    answer = "Мок-ответ на вопрос: " + text
    audio_file = YandexSpeech.text_to_speech(answer)
    SIPuniService.play_audio(call_id, f"{settings.BASE_URL}/audio/{audio_file}")

async def generate_and_play_response(call_id: str, question: str):
    # Моковый поиск по базе (FIXED_RESPONSE)
    context = "\n".join([f"{i+1}. {item['text']}" for i, item in enumerate(FIXED_RESPONSE)])
    prompt = f"Клиент: {question}\nКонтекст:\n{context}\nОтвет:"
    answer = await DeepSeekAI.generate_response(prompt)
    audio_file = await YandexSpeech.text_to_speech(answer)
    await SIPuniService.play_audio(call_id, f"{settings.BASE_URL}/audio/{audio_file}")