import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    def __init__(self):
        self.SIPUNI_API_KEY = os.environ.get('SIPUNI_API_KEY', '')
        self.SIPUNI_SIP_ID = os.environ.get('SIPUNI_SIP_ID', '')
        self.YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY', '')
        self.YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID', '')
        self.DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', None)
        self.BASE_URL = os.environ.get('BASE_URL', 'https://qdrant-ci3r.onrender.com')

settings = Settings()