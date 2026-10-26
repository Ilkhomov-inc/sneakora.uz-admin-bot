import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini").strip().lower()

    # Gemini settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # OpenAI settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "").strip() or None
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    # Shop & Template settings
    SHOP_NAME: str = os.getenv("SHOP_NAME", "SNEAKORA").strip()
    ADMIN_HANDLE: str = os.getenv("ADMIN_HANDLE", "@sneakora_admin").strip()
    PRICE_MODE: str = os.getenv("PRICE_MODE", "placeholder").strip().lower()
    DEFAULT_SIZES: str = os.getenv("DEFAULT_SIZES", "Все размеры").strip()

    # Allowed users (comma-separated Telegram IDs)
    _allowed_raw: str = os.getenv("ALLOWED_USERS", "").strip()
    ALLOWED_USERS: set = set()
    if _allowed_raw:
        for uid in _allowed_raw.split(","):
            uid = uid.strip()
            if uid.isdigit():
                ALLOWED_USERS.add(int(uid))

    @classmethod
    def is_user_allowed(cls, user_id: int) -> bool:
        if not cls.ALLOWED_USERS:
            return True
        return user_id in cls.ALLOWED_USERS


config = Config()
