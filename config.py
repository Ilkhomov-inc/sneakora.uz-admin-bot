import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _parse_ids(raw: str) -> set:
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}


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

    # Access control (comma-separated Telegram IDs)
    # ADMIN_IDS — получают заявки и управляют доступом через /users
    # ALLOWED_USERS — постоянный доступ без заявки
    ADMIN_IDS: set = _parse_ids(os.getenv("ADMIN_IDS", ""))
    ALLOWED_USERS: set = _parse_ids(os.getenv("ALLOWED_USERS", ""))

    # Одобренные пользователи и заявки хранятся здесь (не перезаписывается при деплое)
    DATA_DIR: Path = BASE_DIR / "data"


config = Config()
