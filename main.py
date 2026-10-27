import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import config
from handlers import router
from access import router as access_router, AccessMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sneakora_bot")


async def main():
    if not config.BOT_TOKEN:
        logger.error(
            "\n"
            "==========================================================\n"
            " ОШИБКА: Токен Telegram бота не указан!\n"
            " 1. Откройте файл .env в папке бота\n"
            " 2. Укажите BOT_TOKEN=ваш_токен_из_BotFather\n"
            " 3. Укажите GEMINI_API_KEY=ваш_ключ (или OPENAI_API_KEY)\n"
            "=========================================================="
        )
        return

    logger.info("Инициализация бота %s...", config.SHOP_NAME)
    logger.info("Выбранный ИИ провайдер: %s", config.AI_PROVIDER)

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    if not config.ADMIN_IDS:
        logger.warning("ADMIN_IDS не задан в .env — заявки на доступ некому одобрять!")

    # Заявки и управление доступом — без проверки; рабочие хэндлеры — только для одобренных
    router.message.outer_middleware(AccessMiddleware())
    router.callback_query.outer_middleware(AccessMiddleware())
    dp.include_router(access_router)
    dp.include_router(router)

    # Удаляем вебхуки и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и ожидает сообщений...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Работа бота завершена пользователем.")
