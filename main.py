import os
import asyncio
import json
import uuid
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Optional
import openai
import aiohttp
import base64
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Конфигурация SIPuni
SIPUNI_API_KEY = os.getenv("SIPUNI_API_KEY")  # Получить в ЛК SIPuni
SIPUNI_SIP_ID = os.getenv("SIPUNI_SIP_ID")    # Ваш SIP-аккаунт (например "sip12345")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("BASE_URL")  # Адрес вашего сервера

# Фиксированные тестовые данные
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

# Состояния звонков
class CallState:
    def __init__(self):
        self.websocket: Optional[WebSocket] = None
        self.dialog_history: list = []
        self.last_activity: float = time.time()
        self.recognition_active: bool = False
        self.audio_buffer: bytes = b""
        self.current_question: str = ""
        self.waiting_for_response: bool = False
        self.call_id: Optional[str] = None

active_calls: Dict[str, CallState] = {}

# Модели данных
class CallRequest(BaseModel):
    phone_number: str

class VoiceResponse(BaseModel):
    call_id: str
    text: str

# Утилиты для работы с SIPuni API
async def sipuni_api_request(endpoint: str, data: dict):
    """Отправка запроса к API SIPuni"""
    url = f"https://sipuni.com/api{endpoint}"
    data['secret'] = SIPUNI_API_KEY
    headers = {"Content-Type": "application/json"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            return await response.json()

# API для тестового звонка
@app.post("/initiate_test_call")
async def initiate_test_call():
    """Инициирует тестовый звонок на ваш номер"""
    try:
        call_id = str(uuid.uuid4())
        active_calls[call_id] = CallState()
        active_calls[call_id].call_id = call_id
        
        # Инициируем звонок через SIPuni API
        response = await sipuni_api_request(
            "/callback/call_number",
            {
                "phone": "89054206499",  # Ваш номер для теста
                "sipnumber": SIPUNI_SIP_ID,
                "callerid": "RobotMVP",
                "webhook": f"{BASE_URL}/sipuni_events",
                "custom_data": call_id
            }
        )
        
        if response.get("result") != "success":
            raise HTTPException(status_code=500, detail="SIPuni call failed")
        
        return {"status": "call_initiated", "call_id": call_id}
    except Exception as e:
        logger.error(f"Call initiation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Вебхук для событий SIPuni
@app.post("/sipuni_events")
async def sipuni_events(request: Request):
    """Обрабатывает события от SIPuni API"""
    data = await request.json()
    call_id = data.get("custom_data")
    
    if not call_id or call_id not in active_calls:
        return JSONResponse(content={"status": "unknown_call"})
    
    state = active_calls[call_id]
    
    if data.get("status") == "answered":
        # Вызов ответлен
        logger.info(f"Call answered: {call_id}")
        state.recognition_active = True
        
    elif data.get("record_url"):
        # Доступна запись аудио
        await process_audio_fragment(call_id, data["record_url"])
    
    elif data.get("status") in ("finished", "failed"):
        # Звонок завершен
        logger.info(f"Call ended: {call_id}")
        if call_id in active_calls:
            del active_calls[call_id]
    
    return JSONResponse(content={"status": "processed"})

# Обработка аудио
async def process_audio_fragment(call_id: str, audio_url: str):
    """Обрабатывает аудиофрагмент"""
    if call_id not in active_calls:
        return
    
    state = active_calls[call_id]
    
    try:
        # Скачиваем аудио
        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url) as resp:
                audio_data = await resp.read()
        
        # Распознаем через Yandex SpeechKit
        text = await speech_to_text(audio_data)
        state.current_question = text
        await handle_question(call_id)
        
    except Exception as e:
        logger.error(f"Audio processing error: {str(e)}")

async def speech_to_text(audio_data: bytes) -> str:
    """Конвертирует аудио в текст с помощью Yandex SpeechKit"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID
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

async def handle_question(call_id: str):
    """Обрабатывает вопрос и генерирует ответ"""
    if call_id not in active_calls:
        return
    
    state = active_calls[call_id]
    state.waiting_for_response = True
    
    try:
        # 1. Фиксированный "поиск" в Qdrant (мок)
        context = "Контекст для ответа:\n"
        for i, item in enumerate(FIXED_RESPONSE):
            context += f"{i+1}. {item['text']} (Тип: {item['tags']})\n"
        
        # 2. Генерация ответа с помощью DeepSeek
        prompt = f"""
        Клиент спросил: "{state.current_question}"
        
        Доступная информация:
        {context}
        
        Сформируй краткий дружелюбный ответ на русском без технических деталей.
        """
        
        response = openai.ChatCompletion.create(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        answer_text = response.choices[0].message.content
        state.dialog_history.append(f"Клиент: {state.current_question}")
        state.dialog_history.append(f"Бот: {answer_text}")
        
        # 3. Озвучка ответа
        audio_url = await text_to_speech(answer_text)
        await sipuni_play_audio(call_id, audio_url)
        
    except Exception as e:
        logger.error(f"Response generation error: {str(e)}")
        error_audio = await text_to_speech("Извините, произошла ошибка.")
        await sipuni_play_audio(call_id, error_audio)
    finally:
        state.waiting_for_response = False

async def text_to_speech(text: str) -> str:
    """Конвертирует текст в аудио с помощью Yandex SpeechKit"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID
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
                    return f"{BASE_URL}/audio/{filename}"
                else:
                    error = await response.text()
                    logger.error(f"TTS error: {error}")
                    return ""
    except Exception as e:
        logger.error(f"TTS request error: {str(e)}")
        return ""

async def sipuni_play_audio(call_id: str, audio_url: str):
    """Воспроизводит аудио через SIPuni API"""
    if call_id not in active_calls:
        return
    
    try:
        await sipuni_api_request(
            "/callback/play",
            {
                "call_id": active_calls[call_id].call_id,
                "audio_url": audio_url,
                "silence_detect": True
            }
        )
    except Exception as e:
        logger.error(f"SIPuni play audio error: {str(e)}")

# Запуск сервера
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)