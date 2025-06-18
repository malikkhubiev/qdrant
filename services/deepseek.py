import openai
import logging
from config import settings

logger = logging.getLogger(__name__)

class DeepSeekAI:
    @staticmethod
    async def generate_response(prompt: str) -> str:
        try:
            response = openai.ChatCompletion.create(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI error: {str(e)}")
            return "Извините, произошла ошибка."