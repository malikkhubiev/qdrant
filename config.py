import os
from dotenv import load_dotenv
load_dotenv()
from pydantic import BaseSettings

class Settings(BaseSettings):
    SIPUNI_API_KEY: str
    SIPUNI_SIP_ID: str
    YANDEX_API_KEY: str
    YANDEX_FOLDER_ID: str
    DEEPSEEK_API_KEY: str
    BASE_URL: str = "https://qdrant-ci3r.onrender.com"
    
    class Config:
        env_file = ".env"

settings = Settings()