import io
import html
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

def get_instruction_text() -> str:
    """Пошаговая инструкция, которую бот показывает по /start и /help."""
    return (
        f"📖 <b>Инструкция — как сделать пост для канала {config.SHOP_NAME}</b>\n\n"
        f"<b>Шаг 1. Отправь кроссовки</b>\n"
        f"📸 Скинь фото кроссовок (можно альбом — бот возьмёт первое фото)\n"
        f"или ✍️ напиши название модели текстом, например:\n"
        f"<code>Nike Dunk Low Panda</code>\n\n"
        f"<b>Шаг 2. Добавь подсказку (необязательно)</b>\n"
        f"💡 В подписи к фото можно указать пол, размеры и цену:\n"
        f"<code>женские 36-40 цена 70$</code>\n\n"
        f"<b>Шаг 3. Проверь и допиши цену</b>\n"
        f"Бот пришлёт готовый пост по шаблону. Под ним кнопки:\n"
        f"💰 <b>Указать цену</b> — нажми и отправь цену (<code>65$</code> или просто <code>65</code>), пост обновится\n"
        f"📋 <b>Текст для копирования</b> — один тап по тексту копирует пост целиком\n\n"
        f"<b>Шаг 4. Опубликуй</b>\n"
        f"📤 Перешли готовое фото с подписью в канал (Переслать → «Скрыть отправителя»)\n"
        f"или вставь скопированный текст.\n\n"
        f"⚠️ Если бот ошибся с моделью — отправь фото ещё раз с точным названием в подписи, "
        f"например <code>Nike Dunk Low SP Plum</code>.\n\n"
        f"Команды:\n"
        f"/start — инструкция\n"
        f"/template — пример готового поста\n"
        f"/help — инструкция"
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    greeting = f"👋 Привет, {html.escape(message.from_user.first_name or '')}!\n\n"
    await message.answer(greeting + get_instruction_text(), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(get_instruction_text(), parse_mode="HTML")


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
