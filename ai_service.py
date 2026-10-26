import base64
import json
import logging
import re
from typing import Optional, Tuple
from config import config
from template import SneakerData

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты — профессиональный эксперт по кроссовкам и сникер-культуре для магазина SNEAKORA.
Твоя задача — точно определить модель кроссовок по фото или текстовому запросу и вернуть структурированные данные.

Правила:
1. "brand": Бренд заглавными буквами (например: NIKE, ADIDAS, NEW BALANCE, ASICS, JORDAN, PUMA, REEBOK, SALOMON, VANS, CONVERSE, HOKA).
2. "model": Точное официальное название модели кроссовок и колорвея (например: "W AIR FORCE 1 '07", "DUNK LOW PANDA", "530 WHITE SILVER", "GEL-KAYANO 14", "SAMBA OG").
3. "gender_type": Тип кроссовок на русском: "Женская", "Мужская" или "Унисекс". (Если в запросе пользователя прямо указан пол — используй его!).
4. "sizes": По умолчанию "Все размеры", НО если пользователь в подписи указал размеры (например, "36-41", "39-45", "40-44"), укажи их.
5. "colors": Основные цвета расцветки на русском языке через слэш " / " с заглавной буквы (например: "Белый / Кремовый / Пыльно-розовый", "Черный / Белый", "Серый / Серебристый").
6. "price": Если пользователь в тексте прямо написал цену (например "цена 65$", "55$", "7000 руб"), извлеки её. Иначе строго null.

Ответ должен быть ИСКЛЮЧИТЕЛЬНО в формате JSON без лишнего текста:
{
  "brand": "NIKE",
  "model": "W AIR FORCE 1 '07",
  "gender_type": "Женская",
  "sizes": "Все размеры",
  "colors": "Белый / Кремовый / Пыльно-розовый",
  "price": null
}
"""


def clean_json_response(raw_text: str) -> dict:
    """Очищает ответ модели от markdown-разметки и парсит JSON."""
    text = raw_text.strip()
    # Убираем markdown обертку ```json ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Попытка найти JSON объект внутри текста regex'ом
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Не удалось распознать JSON в ответе: {raw_text[:200]}")


class AIService:
    def __init__(self):
        self.provider = config.AI_PROVIDER
        self.gemini_client = None
        self.openai_client = None

        if self.provider == "gemini":
            if not config.GEMINI_API_KEY:
                logger.warning("GEMINI_API_KEY не установлен в .env!")
            else:
                from google import genai
                self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)

        elif self.provider == "openai":
            if not config.OPENAI_API_KEY:
                logger.warning("OPENAI_API_KEY не установлен в .env!")
            else:
                from openai import AsyncOpenAI
                self.openai_client = AsyncOpenAI(
                    api_key=config.OPENAI_API_KEY,
                    base_url=config.OPENAI_BASE_URL,
                )

    async def analyze_image(self, image_bytes: bytes, caption_hint: Optional[str] = None) -> SneakerData:
        """Анализирует фотографию кроссовок и возвращает SneakerData."""
        hint_text = f"\nПодсказка/пожелание от пользователя: {caption_hint}" if caption_hint else ""
        prompt = f"{SYSTEM_PROMPT}\n{hint_text}\nОпредели кроссовки на фото и верни JSON:"

        if self.provider == "gemini":
            return await self._analyze_image_gemini(image_bytes, prompt)
        elif self.provider == "openai":
            return await self._analyze_image_openai(image_bytes, prompt)
        else:
            raise ValueError(f"Неизвестный AI_PROVIDER: {self.provider}")

    async def analyze_text(self, query: str) -> SneakerData:
        """Определяет характеристики кроссовок по текстовому запросу или названию."""
        prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"Запрос пользователя: \"{query}\"\n"
            f"Найди эту модель кроссовок в базе знаний, определи бренд, точное название, тип, цвета и верни JSON:"
        )

        if self.provider == "gemini":
            return await self._analyze_text_gemini(prompt)
        elif self.provider == "openai":
            return await self._analyze_text_openai(prompt)
        else:
            raise ValueError(f"Неизвестный AI_PROVIDER: {self.provider}")

    # =========================================================================
    # Gemini Реализация
    # =========================================================================
    async def _analyze_image_gemini(self, image_bytes: bytes, prompt: str) -> SneakerData:
        if not self.gemini_client:
            raise RuntimeError("Gemini API ключ не настроен. Укажите GEMINI_API_KEY в файле .env")

        from google.genai import types
        # Запуск в фоновом executor, так как SDK синхронный для генерации
        import asyncio
        loop = asyncio.get_running_loop()

        def _call_gemini():
            return self.gemini_client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt,
                ],
            )

        response = await loop.run_in_executor(None, _call_gemini)
        data_dict = clean_json_response(response.text)
        return self._dict_to_sneaker_data(data_dict)

    async def _analyze_text_gemini(self, prompt: str) -> SneakerData:
        if not self.gemini_client:
            raise RuntimeError("Gemini API ключ не настроен. Укажите GEMINI_API_KEY в файле .env")

        import asyncio
        loop = asyncio.get_running_loop()

        def _call_gemini():
            return self.gemini_client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )

        response = await loop.run_in_executor(None, _call_gemini)
        data_dict = clean_json_response(response.text)
        return self._dict_to_sneaker_data(data_dict)

    # =========================================================================
    # OpenAI Реализация
    # =========================================================================
    async def _analyze_image_openai(self, image_bytes: bytes, prompt: str) -> SneakerData:
        if not self.openai_client:
            raise RuntimeError("OpenAI API ключ не настроен. Укажите OPENAI_API_KEY в файле .env")

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        response = await self.openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            temperature=0.2,
        )
        raw_text = response.choices[0].message.content
        data_dict = clean_json_response(raw_text)
        return self._dict_to_sneaker_data(data_dict)

    async def _analyze_text_openai(self, prompt: str) -> SneakerData:
        if not self.openai_client:
            raise RuntimeError("OpenAI API ключ не настроен. Укажите OPENAI_API_KEY в файле .env")

        response = await self.openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw_text = response.choices[0].message.content
        data_dict = clean_json_response(raw_text)
        return self._dict_to_sneaker_data(data_dict)

    # =========================================================================
    # Вспомогательный метод преобразования в SneakerData
    # =========================================================================
    def _dict_to_sneaker_data(self, d: dict) -> SneakerData:
        return SneakerData(
            brand=d.get("brand", "SNEAKERS"),
            model=d.get("model", "Original"),
            gender_type=d.get("gender_type", "Унисекс"),
            sizes=d.get("sizes") or config.DEFAULT_SIZES,
            colors=d.get("colors", "Оригинальный"),
            price=d.get("price"),
        )


ai_service = AIService()
