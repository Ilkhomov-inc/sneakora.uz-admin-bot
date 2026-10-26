import io
import time
import logging
from typing import Optional, Dict

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import config
from template import SneakerData, format_sneaker_post
from ai_service import ai_service

logger = logging.getLogger(__name__)
router = Router()

# Кэш медиа-групп (альбомов) для предотвращения дублирования запросов к ИИ
_processed_media_groups: Dict[str, float] = {}


class FormStates(StatesGroup):
    waiting_for_price = State()


def get_post_keyboard(has_price: bool = False) -> InlineKeyboardMarkup:
    """Генерирует инлайн-кнопки под сформированным постом."""
    buttons = [
        [
            InlineKeyboardButton(
                text="💰 " + ("Изменить цену" if has_price else "Указать цену"),
                callback_data="set_price",
            ),
            InlineKeyboardButton(
                text="📋 Текст для копирования",
                callback_data="copy_text",
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =========================================================================
# Команды бота
# =========================================================================

@router.message(CommandStart())
async def cmd_start(message: Message):
    if not config.is_user_allowed(message.from_user.id):
        await message.answer("⛔ Извините, у вас нет доступа к этому рабочему боту команды.")
        return

    provider_name = "Google Gemini" if config.AI_PROVIDER == "gemini" else "OpenAI"
    text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я бот команды **{config.SHOP_NAME}** для быстрого создания постов с кроссовками.\n\n"
        f"⚡ **Что я умею:**\n"
        f"1. 📸 **Скинь мне фото кроссовок** (или альбом) — я распознаю модель через ИИ и сделаю готовый пост по шаблону.\n"
        f"2. ✍️ **Напиши название модели текстом** (например: `Nike Dunk Low Panda` или `Asics Gel-Kayano 14`) — я найду характеристики и заполню шаблон.\n"
        f"3. 💡 К фото можно сразу добавить подпись: например `36-40, женские` или `цена 65$`.\n\n"
        f"⚙️ **Текущий ИИ:** {provider_name}\n"
        f"💰 **Режим цены:** {config.PRICE_MODE}\n"
        f"👤 **Админ:** {config.ADMIN_HANDLE}\n\n"
        f"🚀 Просто отправь фото или название модели прямо сейчас!"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not config.is_user_allowed(message.from_user.id):
        return

    text = (
        f"📖 **Инструкция по использованию:**\n\n"
        f"• **Фото кроссовок:** Отправь одну или несколько фотографий. Бот возьмет первое четкое фото, распознает силуэт, расцветку и заполнит шаблон.\n"
        f"• **Подсказки в подписи:** Если написать в подписи к фото, например: `цена 60$ женские 36-40`, бот учтет это при формировании поста.\n"
        f"• **Поиск по названию:** Можно просто написать `Nike Air Jordan 4 Retro White Cement` — бот найдет точные цвета и характеристики.\n"
        f"• **Кнопка 'Указать цену':** Позволяет в 1 клик добавить точную стоимость, если вы ее еще не ставили.\n"
        f"• **Кнопка 'Текст для копирования':** Выдает пост в моноширинном блоке — один тап по нему на телефоне копирует весь текст целиком!\n\n"
        f"Команды:\n"
        f"/start — Перезапуск бота\n"
        f"/template — Посмотреть текущий шаблон\n"
        f"/help — Эта справка"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("template"))
async def cmd_template(message: Message):
    sample = SneakerData(
        brand="NIKE",
        model="W AIR FORCE 1 '07",
        gender_type="Женская",
        sizes="Все размеры",
        colors="Белый / Кремовый / Пыльно-розовый",
        price="62$",
    )
    post_text = format_sneaker_post(sample)
    await message.answer(
        f"📌 **Текущий шаблон постов для канала:**\n\n{post_text}",
        parse_mode=None,
    )


# =========================================================================
# Обработка фотографий
# =========================================================================

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot, state: FSMContext):
    if not config.is_user_allowed(message.from_user.id):
        await message.answer("⛔ Доступ ограничен.")
        return

    # Защита от спама альбомами (обрабатываем только первое фото из альбома)
    now = time.time()
    if message.media_group_id:
        if message.media_group_id in _processed_media_groups:
            # Уже обрабатываем эту группу
            return
        _processed_media_groups[message.media_group_id] = now
        # Очистка старых записей
        for k in list(_processed_media_groups.keys()):
            if now - _processed_media_groups[k] > 60:
                _processed_media_groups.pop(k, None)

    status_msg = await message.answer("🔍 Распознаю модель кроссовок и ищу характеристики...")

    try:
        # Скачиваем фото в наилучшем разрешении
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes_io = io.BytesIO()
        await bot.download_file(file_info.file_path, destination=photo_bytes_io)
        image_bytes = photo_bytes_io.getvalue()

        # Отправляем в ИИ
        caption_hint = message.caption
        sneaker_data = await ai_service.analyze_image(image_bytes, caption_hint=caption_hint)

        # Формируем пост
        post_text = format_sneaker_post(sneaker_data)

        # Сохраняем в FSM данные последнего распознавания
        await state.update_data(
            last_post=post_text,
            sneaker_brand=sneaker_data.brand,
            sneaker_model=sneaker_data.model,
            gender_type=sneaker_data.gender_type,
            sizes=sneaker_data.sizes,
            colors=sneaker_data.colors,
            price=sneaker_data.price,
            photo_file_id=photo.file_id,
        )

        has_price = bool(sneaker_data.price)
        keyboard = get_post_keyboard(has_price=has_price)

        await status_msg.delete()

        # Отправляем фото с готовой подписью (удобно сразу переслать в канал!)
        await message.reply_photo(
            photo=photo.file_id,
            caption=post_text,
            reply_markup=keyboard,
        )

    except Exception as e:
        logger.exception("Ошибка при обработке фото: %s", e)
        await status_msg.edit_text(
            f"❌ Не удалось распознать модель.\n\n"
            f"Причина: `{str(e)}`\n\n"
            f"Попробуйте отправить другое фото или напишите название модели текстом.",
            parse_mode="Markdown",
        )


# =========================================================================
# Обработка текстовых запросов
# =========================================================================

@router.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext):
    if not config.is_user_allowed(message.from_user.id):
        await message.answer("⛔ Доступ ограничен.")
        return

    # Проверяем, не ждем ли мы ввод цены
    current_state = await state.get_state()
    if current_state == FormStates.waiting_for_price:
        await process_price_input(message, state)
        return

    status_msg = await message.answer("🔍 Ищу модель в базе знаний и составляю шаблон...")

    try:
        sneaker_data = await ai_service.analyze_text(message.text)
        post_text = format_sneaker_post(sneaker_data)

        # Сохраняем в состояние
        await state.update_data(
            last_post=post_text,
            sneaker_brand=sneaker_data.brand,
            sneaker_model=sneaker_data.model,
            gender_type=sneaker_data.gender_type,
            sizes=sneaker_data.sizes,
            colors=sneaker_data.colors,
            price=sneaker_data.price,
            photo_file_id=None,
        )

        has_price = bool(sneaker_data.price)
        keyboard = get_post_keyboard(has_price=has_price)

        await status_msg.delete()
        await message.reply(post_text, reply_markup=keyboard)

    except Exception as e:
        logger.exception("Ошибка при обработке текста: %s", e)
        await status_msg.edit_text(
            f"❌ Произошла ошибка при поиске модели.\n\n"
            f"Причина: `{str(e)}`",
            parse_mode="Markdown",
        )


# =========================================================================
# Callback кнопки: указание цены и копирование
# =========================================================================

@router.callback_query(F.data == "set_price")
async def callback_set_price(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FormStates.waiting_for_price)
    await callback.message.reply(
        "💵 **Введите цену для этого товара**\n"
        "(например: `65$` или `6000 ₽` или просто число `70`):",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "copy_text")
async def callback_copy_text(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_text = data.get("last_post")

    if not post_text:
        # Если в FSM нет, берем текст/подпись сообщения
        post_text = callback.message.caption or callback.message.text or ""

    if post_text:
        # Оборачиваем в моноширинный блок ``` чтобы по тапу копировалось в буфер обмена
        msg_text = (
            "📋 **Нажмите на текст ниже, чтобы скопировать его целиком:**\n\n"
            f"```\n{post_text}\n```"
        )
        await callback.message.reply(msg_text, parse_mode="Markdown")
    else:
        await callback.message.reply("Текст не найден. Сгенерируйте пост заново.")

    await callback.answer()


async def process_price_input(message: Message, state: FSMContext):
    """Обрабатывает введенную пользователем цену и обновляет пост."""
    user_price = message.text.strip()
    data = await state.get_data()

    brand = data.get("sneaker_brand", "SNEAKERS")
    model = data.get("sneaker_model", "Original")
    gender = data.get("gender_type", "Унисекс")
    sizes = data.get("sizes", config.DEFAULT_SIZES)
    colors = data.get("colors", "Оригинальный")
    photo_file_id = data.get("photo_file_id")

    sneaker_data = SneakerData(
        brand=brand,
        model=model,
        gender_type=gender,
        sizes=sizes,
        colors=colors,
        price=user_price,
    )

    updated_post = format_sneaker_post(sneaker_data, custom_price=user_price)
    await state.update_data(last_post=updated_post, price=user_price)
    await state.set_state(None)  # сбрасываем состояние

    keyboard = get_post_keyboard(has_price=True)

    if photo_file_id:
        await message.reply_photo(
            photo=photo_file_id,
            caption=updated_post,
            reply_markup=keyboard,
        )
    else:
        await message.reply(updated_post, reply_markup=keyboard)
