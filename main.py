from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import calls, events
from config import settings
import logging
from fastapi.responses import FileResponse
import os

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(calls.router, prefix="/api/calls")
app.include_router(events.router, prefix="/api/events")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/ogg")
    return {"error": "File not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)