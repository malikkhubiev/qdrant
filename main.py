import os
import asyncio
import json
import uuid
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import openai
import aiohttp
import base64
import time
import hmac
import hashlib

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Конфигурация
MTS_API_KEY = os.getenv("MTS_API_KEY")
MTS_API_SECRET = os.getenv("MTS_API_SECRET")
MTS_VIRTUAL_NUMBER = os.getenv("MTS_VIRTUAL_NUMBER")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
BASE_URL = os.getenv("BASE_URL")  # Адрес вашего сервера

# Инициализация клиентов
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
deepseek_client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")

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
        self.call_session_id: Optional[str] = None

active_calls: Dict[str, CallState] = {}

# Модели данных
class CallRequest(BaseModel):
    phone_number: str

class VoiceResponse(BaseModel):
    call_id: str
    text: str

# Утилиты для работы с МТС Exolve API
def generate_mts_signature(api_key: str, api_secret: str, data: dict) -> str:
    """Генерация подписи для API МТС Exolve"""
    sorted_data = sorted(data.items(), key=lambda x: x[0])
    message = "".join([f"{k}{v}" for k, v in sorted_data]) + api_secret
    return hmac.new(api_key.encode(), message.encode(), hashlib.sha256).hexdigest()

async def mts_api_request(method: str, endpoint: str, data: dict):
    """Отправка запроса к API МТС Exolve"""
    url = f"https://api.exolve.ru{endpoint}"
    signature = generate_mts_signature(MTS_API_KEY, MTS_API_SECRET, data)
    headers = {
        "Authorization": f"Bearer {MTS_API_KEY}:{signature}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        if method == "POST":
            async with session.post(url, json=data, headers=headers) as response:
                return await response.json()
        else:
            async with session.get(url, headers=headers) as response:
                return await response.json()

# Инициализация векторной базы
def init_qdrant_collection():
    try:
        qdrant_client.get_collection("sales_knowledge")
    except Exception:
        qdrant_client.create_collection(
            collection_name="sales_knowledge",
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        # Добавление тестовых данных
        points = [
            {
                "id": 1,
                "vector": [0.1] * 768,
                "payload": {
                    "text": "У нас действует скидка 20% на все продукты до конца месяца",
                    "tags": "discount",
                    "product": "all"
                }
            },
            {
                "id": 2,
                "vector": [0.2] * 768,
                "payload": {
                    "text": "Бесплатная доставка при заказе от 5000 рублей",
                    "tags": "delivery",
                    "product": "all"
                }
            },
            {
                "id": 3,
                "vector": [0.3] * 768,
                "payload": {
                    "text": "Продукт Premium включает дополнительные функции аналитики",
                    "tags": "product_info",
                    "product": "premium"
                }
            }
        ]
        qdrant_client.upsert(collection_name="sales_knowledge", points=points)

# Инициализация при запуске
init_qdrant_collection()

# API для инициирования звонка
@app.post("/initiate_call")
async def initiate_call(request: CallRequest):
    """Инициирует звонок на указанный номер через МТС Exolve"""
    try:
        call_id = str(uuid.uuid4())
        active_calls[call_id] = CallState()
        
        # Инициируем звонок через МТС Exolve API
        response = await mts_api_request(
            "POST",
            "/v1/calls/make",
            data={
                "from": MTS_VIRTUAL_NUMBER,
                "to": request.phone_number,
                "callback_url": f"{BASE_URL}/mts_events",
                "custom_data": call_id,
                "options": {
                    "voice_detection": True,
                    "silence_timeout": 1500  # Пауза 1.5 секунды
                }
            }
        )
        
        if response.get("status") != "success":
            raise HTTPException(status_code=500, detail="MTS call failed")
        
        return {"status": "call_initiated", "call_id": call_id}
    except Exception as e:
        logger.error(f"Call initiation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Вебхук для событий МТС Exolve
@app.post("/mts_events")
async def mts_events(request: Request):
    """Обрабатывает события от МТС Exolve API"""
    data = await request.json()
    event = data.get("event")
    call_id = data.get("custom_data")
    
    if not call_id or call_id not in active_calls:
        return JSONResponse(content={"status": "unknown_call"})
    
    state = active_calls[call_id]
    
    if event == "call.answered":
        # Вызов ответлен
        logger.info(f"Call answered: {call_id}")
        state.call_session_id = data.get("session_id")
        state.recognition_active = True
        
    elif event == "recording.available":
        # Доступна запись аудио
        record_url = data.get("record_url")
        if record_url and state.recognition_active:
            await process_audio_fragment(call_id, record_url)
    
    elif event == "call.finished":
        # Звонок завершен
        logger.info(f"Call ended: {call_id}")
        if call_id in active_calls:
            del active_calls[call_id]
    
    return JSONResponse(content={"status": "processed"})

# WebSocket для потоковой обработки аудио
@app.websocket("/ws/{call_id}")
async def websocket_endpoint(websocket: WebSocket, call_id: str):
    """WebSocket для потоковой передачи аудио и управления диалогом"""
    if call_id not in active_calls:
        await websocket.close(code=1008, reason="Call not found")
        return
    
    state = active_calls[call_id]
    state.websocket = websocket
    await websocket.accept()
    
    try:
        while True:
            # Ожидаем данные: либо аудио, либо команды
            data = await websocket.receive()
            
            if "bytes" in data:
                # Потоковые аудиоданные
                state.audio_buffer += data["bytes"]
                state.last_activity = time.time()
                
                # Проверка на паузу (нет данных в течение 1.5 секунд)
                if len(state.audio_buffer) > 0 and time.time() - state.last_activity > 1.5:
                    await process_audio_buffer(call_id)
            
            elif "text" in data:
                # Текстовые команды
                message = json.loads(data["text"])
                if message.get("type") == "partial_recognition":
                    state.current_question = message["text"]
                elif message.get("type") == "final_recognition":
                    state.current_question = message["text"]
                    await handle_question(call_id)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call: {call_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        if call_id in active_calls:
            active_calls[call_id].websocket = None

async def process_audio_buffer(call_id: str):
    """Обрабатывает накопленный буфер аудио"""
    if call_id not in active_calls:
        return
    
    state = active_calls[call_id]
    if len(state.audio_buffer) == 0:
        return
    
    # Отправляем аудио в Yandex SpeechKit для распознавания
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "x-folder-id": YANDEX_FOLDER_ID,
                "Transfer-Encoding": "chunked"
            }
            
            params = {
                "topic": "general",
                "lang": "ru-RU",
                "model": "general",
                "partialResults": "true"
            }
            
            async with session.post(
                "https://stt.api.cloud.yandex.net/speech/v1/stt:streamingRecognize",
                headers=headers,
                params=params,
                data=state.audio_buffer
            ) as response:
                result = await response.json()
                
                if "result" in result:
                    for chunk in result["result"]["chunks"]:
                        if chunk["final"]:
                            # Финальный результат
                            state.current_question = chunk["alternatives"][0]["text"]
                            await state.websocket.send_text(json.dumps({
                                "type": "final_recognition",
                                "text": state.current_question
                            }))
                        else:
                            # Частичный результат
                            await state.websocket.send_text(json.dumps({
                                "type": "partial_recognition",
                                "text": chunk["alternatives"][0]["text"]
                            }))
    except Exception as e:
        logger.error(f"Speech recognition error: {str(e)}")
    
    # Очищаем буфер
    state.audio_buffer = b""

async def handle_question(call_id: str):
    """Обрабатывает распознанный вопрос"""
    if call_id not in active_calls:
        return
    
    state = active_calls[call_id]
    state.waiting_for_response = True
    
    try:
        # 1. Поиск в Qdrant
        search_results = qdrant_client.search(
            collection_name="sales_knowledge",
            query_vector=[0.1] * 768,  # В реальности: вектор запроса
            limit=3
        )
        
        # Подготавливаем контекст
        context = "Контекст для ответа:\n"
        for i, hit in enumerate(search_results):
            context += f"{i+1}. {hit.payload['text']} (Тип: {hit.payload.get('tags', '')})\n"
        
        # 2. Генерация ответа с помощью DeepSeek
        prompt = f"""
        Ты менеджер по продажам. Отвечай на вопрос клиента, используя контекст.
        Текущий диалог:
        {state.dialog_history[-3:] if state.dialog_history else 'Нет истории'}
        
        Вопрос клиента: {state.current_question}
        
        {context}
        
        Ответ должен быть:
        - Кратким и по делу
        - Вежливым и дружелюбным
        - На русском языке
        - Без технических деталей
        """
        
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты профессиональный менеджер по продажам."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        
        answer_text = response.choices[0].message.content
        
        # Обновляем историю диалога
        state.dialog_history.append(f"Клиент: {state.current_question}")
        state.dialog_history.append(f"Бот: {answer_text}")
        
        # 3. Синтез речи через Yandex SpeechKit
        audio_url = await text_to_speech(answer_text)
        
        # 4. Воспроизведение ответа через МТС Exolve
        await mts_play_audio(call_id, audio_url)
        
    except Exception as e:
        logger.error(f"Response generation error: {str(e)}")
        # Отправляем сообщение об ошибке
        error_audio = await text_to_speech("Извините, произошла ошибка. Пожалуйста, повторите вопрос.")
        await mts_play_audio(call_id, error_audio)
    finally:
        state.waiting_for_response = False
        state.current_question = ""

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
                "voice": "alena",  # Голос Алена
                "emotion": "good",  # Доброжелательная интонация
                "format": "oggopus",
                "sampleRateHertz": 48000
            }
            
            async with session.post(
                "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                headers=headers,
                data=data
            ) as response:
                if response.status == 200:
                    # Сохраняем аудио во временный файл
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

async def mts_play_audio(call_id: str, audio_url: str):
    """Воспроизводит аудио через МТС Exolve API"""
    if call_id not in active_calls or not active_calls[call_id].call_session_id:
        return
    
    try:
        # Отправляем команду на воспроизведение
        await mts_api_request(
            "POST",
            "/v1/calls/play",
            data={
                "session_id": active_calls[call_id].call_session_id,
                "audio_url": audio_url,
                "options": {
                    "repeat": False,
                    "silence_after": 1500  # Пауза после воспроизведения
                }
            }
        )
    except Exception as e:
        logger.error(f"MTS play audio error: {str(e)}")

# API для управления диалогом
@app.post("/send_response")
async def send_response(response: VoiceResponse):
    """Отправляет текстовый ответ в диалог (для отладки)"""
    if response.call_id not in active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    
    state = active_calls[response.call_id]
    state.dialog_history.append(f"Оператор: {response.text}")
    
    if state.websocket:
        await state.websocket.send_text(json.dumps({
            "type": "agent_message",
            "text": response.text
        }))
    
    return {"status": "message_sent"}

# Запуск сервера
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, ws_ping_interval=10, ws_ping_timeout=30)