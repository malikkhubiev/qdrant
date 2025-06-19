import logging

logger = logging.getLogger(__name__)

class DeepSeekAI:
    @staticmethod
    async def generate_response(prompt: str) -> str:
        # Мок: возвращаем фиксированный ответ
        return "Мок-ответ DeepSeekAI"