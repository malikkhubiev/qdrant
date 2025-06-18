import os
import asyncio
import json
import uuid
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Optional
import openai
import aiohttp
import base64
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Конфигурация SIPuni
SIPUNI_API_KEY = os.getenv("SIPUNI_API_KEY")  # Получить в ЛК SIPuni
SIPUNI_SIP_ID = os.getenv("SIPUNI_SIP_ID")    # Ваш SIP-аккаунт (например "sip12345")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("BASE_URL")  # Адрес вашего сервера

# Логирование конфигурации
logger.info(f"Starting application with configuration:")
logger.info(f"SIPUNI_SIP_ID: {SIPUNI_SIP_ID}")
logger.info(f"BASE_URL: {BASE_URL}")
logger.info(f"YANDEX_FOLDER_ID: {YANDEX_FOLDER_ID}")

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

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint that shows the service is working"""
    logger.info("Accessed root endpoint")
    return """
    <html>
        <head>
            <title>Call Center AI Service</title>
        </head>
        <body>
            <h1>Call Center AI Service is working correctly!</h1>
            <p>All systems operational.</p>
        </body>
    </html>
    """

# Утилиты для работы с SIPuni API
async def sipuni_api_request(endpoint: str, data: dict):
    """Улучшенный запрос к SIPuni API с обработкой ошибок"""
    url = f"https://sipuni.com/api{endpoint}"
    data['secret'] = SIPUNI_API_KEY
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    logger.info(f"Making SIPuni API request to {endpoint}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                # Проверяем Content-Type
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    text = await response.text()
                    logger.error(f"Non-JSON response from SIPuni: {text[:200]}")
                    if "login" in text:
                        raise HTTPException(
                            status_code=401,
                            detail="Invalid SIPuni API key or SIP ID"
                        )
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail=f"SIPuni returned HTML: {text[:200]}..."
                        )
                
                response_data = await response.json()
                logger.debug(f"SIPuni API response: {response_data}")
                return response_data
                
    except Exception as e:
        logger.error(f"SIPuni API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"SIPuni API request failed: {str(e)}"
        )

# API для тестового звонка
@app.post("/initiate_test_call")
async def initiate_test_call():
    """Инициирует тестовый звонок на ваш номер"""
    logger.info("Initiating test call")
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
            logger.error(f"SIPuni call failed: {response}")
            raise HTTPException(status_code=500, detail="SIPuni call failed")
        
        logger.info(f"Call initiated successfully, call_id: {call_id}")
        return {"status": "call_initiated", "call_id": call_id}
    except Exception as e:
        logger.error(f"Call initiation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Вебхук для событий SIPuni
@app.post("/sipuni_events")
async def sipuni_events(request: Request):
    """Обрабатывает события от SIPuni API"""
    try:
        data = await request.json()
        logger.info(f"Received SIPuni event: {data}")
        call_id = data.get("custom_data")
        
        if not call_id or call_id not in active_calls:
            logger.warning(f"Unknown call_id in SIPuni event: {call_id}")
            return JSONResponse(content={"status": "unknown_call"})
        
        state = active_calls[call_id]
        
        if data.get("status") == "answered":
            # Вызов ответлен
            logger.info(f"Call answered: {call_id}")
            state.recognition_active = True
            
        elif data.get("record_url"):
            # Доступна запись аудио
            logger.info(f"Received audio record URL for call {call_id}")
            await process_audio_fragment(call_id, data["record_url"])
        
        elif data.get("status") in ("finished", "failed"):
            # Звонок завершен
            logger.info(f"Call ended: {call_id}, status: {data.get('status')}")
            if call_id in active_calls:
                del active_calls[call_id]
        
        return JSONResponse(content={"status": "processed"})
    except Exception as e:
        logger.error(f"Error processing SIPuni event: {str(e)}", exc_info=True)
        return JSONResponse(content={"status": "error"}, status_code=500)

# Обработка аудио
async def process_audio_fragment(call_id: str, audio_url: str):
    """Обрабатывает аудиофрагмент"""
    logger.info(f"Processing audio fragment for call {call_id}")
    if call_id not in active_calls:
        logger.warning(f"Call {call_id} not found in active calls")
        return
    
    state = active_calls[call_id]
    
    try:
        # Скачиваем аудио
        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url) as resp:
                audio_data = await resp.read()
                logger.debug(f"Downloaded audio fragment, size: {len(audio_data)} bytes")
        
        # Распознаем через Yandex SpeechKit
        text = await speech_to_text(audio_data)
        logger.info(f"Recognized text: {text}")
        state.current_question = text
        await handle_question(call_id)
        
    except Exception as e:
        logger.error(f"Audio processing error: {str(e)}", exc_info=True)

async def speech_to_text(audio_data: bytes) -> str:
    """Конвертирует аудио в текст с помощью Yandex SpeechKit"""
    logger.info("Starting speech to text conversion")
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
                logger.info(f"Speech recognition result: {result}")
                return result.get("result", "")
    except Exception as e:
        logger.error(f"Speech recognition error: {str(e)}", exc_info=True)
        return ""

async def handle_question(call_id: str):
    """Обрабатывает вопрос и генерирует ответ"""
    logger.info(f"Handling question for call {call_id}")
    if call_id not in active_calls:
        logger.warning(f"Call {call_id} not found when handling question")
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
        
        logger.info(f"Sending prompt to DeepSeek: {prompt[:200]}...")
        response = openai.ChatCompletion.create(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        answer_text = response.choices[0].message.content
        logger.info(f"Received answer from DeepSeek: {answer_text}")
        state.dialog_history.append(f"Клиент: {state.current_question}")
        state.dialog_history.append(f"Бот: {answer_text}")
        
        # 3. Озвучка ответа
        audio_url = await text_to_speech(answer_text)
        await sipuni_play_audio(call_id, audio_url)
        
    except Exception as e:
        logger.error(f"Response generation error: {str(e)}", exc_info=True)
        error_audio = await text_to_speech("Извините, произошла ошибка.")
        await sipuni_play_audio(call_id, error_audio)
    finally:
        state.waiting_for_response = False

async def text_to_speech(text: str) -> str:
    """Конвертирует текст в аудио с помощью Yandex SpeechKit"""
    logger.info(f"Converting text to speech: {text[:50]}...")
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
                        audio_data = await response.read()
                        f.write(audio_data)
                    logger.info(f"Audio file saved: {filename}, size: {len(audio_data)} bytes")
                    return f"{BASE_URL}/audio/{filename}"
                else:
                    error = await response.text()
                    logger.error(f"TTS error: {error}")
                    return ""
    except Exception as e:
        logger.error(f"TTS request error: {str(e)}", exc_info=True)
        return ""

async def sipuni_play_audio(call_id: str, audio_url: str):
    """Воспроизводит аудио через SIPuni API"""
    logger.info(f"Playing audio for call {call_id}, URL: {audio_url}")
    if call_id not in active_calls:
        logger.warning(f"Call {call_id} not found when trying to play audio")
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
        logger.info("Audio play request sent to SIPuni")
    except Exception as e:
        logger.error(f"SIPuni play audio error: {str(e)}", exc_info=True)

# Запуск сервера
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)