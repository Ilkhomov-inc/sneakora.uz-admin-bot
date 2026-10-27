import html
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    User,
)

from config import config
from handlers import get_instruction_text

logger = logging.getLogger(__name__)
router = Router()


# =========================================================================
# Хранилище доступа (JSON-файл, переживает перезапуски)
# =========================================================================

class AccessStore:
    def __init__(self, path):
        self.path = path
        self.approved: Dict[str, dict] = {}
        self.pending: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.approved = data.get("approved", {})
            self.pending = data.get("pending", {})
        except (OSError, ValueError) as e:
            logger.error("Не удалось прочитать %s: %s", self.path, e)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"approved": self.approved, "pending": self.pending}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def is_admin(self, user_id: int) -> bool:
        return user_id in config.ADMIN_IDS

    def is_allowed(self, user_id: int) -> bool:
        return (
            self.is_admin(user_id)
            or user_id in config.ALLOWED_USERS
            or str(user_id) in self.approved
        )

    def is_pending(self, user_id: int) -> bool:
        return str(user_id) in self.pending

    def add_pending(self, user: User):
        self.pending[str(user.id)] = {
            "name": user.full_name,
            "username": user.username,
            "requested_at": int(time.time()),
        }
        self._save()

    def approve(self, user_id: int, by: int) -> dict:
        info = self.pending.pop(str(user_id), None)
        if info is None:
            return None
        info.update(approved_at=int(time.time()), approved_by=by)
        self.approved[str(user_id)] = info
        self._save()
        return info

    def reject(self, user_id: int) -> dict:
        info = self.pending.pop(str(user_id), None)
        if info is not None:
            self._save()
        return info

    def revoke(self, user_id: int) -> dict:
        info = self.approved.pop(str(user_id), None)
        if info is not None:
            self._save()
        return info


store = AccessStore(config.DATA_DIR / "access.json")


def describe_user(user_id, info: dict) -> str:
    name = html.escape(info.get("name") or "Без имени")
    username = f" (@{html.escape(info['username'])})" if info.get("username") else ""
    return f'<a href="tg://user?id={user_id}">{name}</a>{username} — ID <code>{user_id}</code>'


# =========================================================================
# Middleware: пропускает к рабочим хэндлерам только одобренных пользователей
# =========================================================================

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or store.is_allowed(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("⛔ У вас нет доступа к боту.", show_alert=True)
        elif isinstance(event, Message):
            await send_no_access(event)
        return None


async def send_no_access(message: Message):
    user_id = message.from_user.id
    if store.is_pending(user_id):
        await message.answer("⏳ Ваша заявка на доступ уже отправлена. Дождитесь решения администратора.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Подать заявку на доступ", callback_data="access:apply")]
    ])
    await message.answer(
        f"🔒 Это рабочий бот команды <b>{html.escape(config.SHOP_NAME)}</b>, доступ только для сотрудников.\n\n"
        f"Нажмите кнопку ниже — администратор получит заявку и откроет вам доступ.\n\n"
        f"Ваш Telegram ID: <code>{user_id}</code>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# =========================================================================
# Подача заявки
# =========================================================================

@router.callback_query(F.data == "access:apply")
async def callback_apply(callback: CallbackQuery, bot: Bot):
    user = callback.from_user
    if store.is_allowed(user.id):
        await callback.answer("✅ У вас уже есть доступ. Отправьте /start", show_alert=True)
        return
    if store.is_pending(user.id):
        await callback.answer("⏳ Заявка уже отправлена, ждите решения.", show_alert=True)
        return
    if not config.ADMIN_IDS:
        logger.error("Заявка от %s, но ADMIN_IDS не задан в .env", user.id)
        await callback.answer("Администратор бота не настроен. Свяжитесь с владельцем.", show_alert=True)
        return

    store.add_pending(user)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"access:approve:{user.id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"access:reject:{user.id}"),
    ]])
    text = f"📝 <b>Новая заявка на доступ</b>\n\n{describe_user(user.id, store.pending[str(user.id)])}"
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.warning("Не удалось отправить заявку админу %s: %s", admin_id, e)

    await callback.message.edit_text("✅ Заявка отправлена! Я напишу вам, как только администратор её рассмотрит.")
    await callback.answer()


# =========================================================================
# Решение администратора
# =========================================================================

def is_admin_event(event: TelegramObject) -> bool:
    return event.from_user is not None and store.is_admin(event.from_user.id)


@router.callback_query(F.data.startswith("access:approve:"), is_admin_event)
async def callback_approve(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.rsplit(":", 1)[1])
    info = store.approve(user_id, by=callback.from_user.id)
    if info is None:
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ <b>Доступ открыт</b>\n\n{describe_user(user_id, info)}\n"
        f"Одобрил: {html.escape(callback.from_user.full_name)}",
        parse_mode="HTML",
    )
    await callback.answer()
    try:
        await bot.send_message(
            user_id,
            "🎉 Доступ открыт! Добро пожаловать в команду.\n\n" + get_instruction_text(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Не удалось уведомить %s об одобрении: %s", user_id, e)


@router.callback_query(F.data.startswith("access:reject:"), is_admin_event)
async def callback_reject(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.rsplit(":", 1)[1])
    info = store.reject(user_id)
    if info is None:
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return

    await callback.message.edit_text(
        f"❌ <b>Заявка отклонена</b>\n\n{describe_user(user_id, info)}\n"
        f"Отклонил: {html.escape(callback.from_user.full_name)}",
        parse_mode="HTML",
    )
    await callback.answer()
    try:
        await bot.send_message(user_id, "❌ К сожалению, заявка на доступ к боту отклонена.")
    except Exception as e:
        logger.warning("Не удалось уведомить %s об отказе: %s", user_id, e)


# =========================================================================
# Управление пользователями: /users
# =========================================================================

def users_list_view():
    if not store.approved:
        return "👥 Одобренных пользователей пока нет.", None

    lines = ["👥 <b>Пользователи с доступом:</b>\n"]
    buttons = []
    for i, (user_id, info) in enumerate(store.approved.items(), start=1):
        lines.append(f"{i}. {describe_user(user_id, info)}")
        buttons.append([InlineKeyboardButton(
            text=f"🚫 Убрать: {(info.get('name') or user_id)[:30]}",
            callback_data=f"access:revoke:{user_id}",
        )])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("users"), is_admin_event)
async def cmd_users(message: Message):
    text, keyboard = users_list_view()
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("access:revoke:"), is_admin_event)
async def callback_revoke(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.rsplit(":", 1)[1])
    info = store.revoke(user_id)
    if info is None:
        await callback.answer("Этого пользователя уже нет в списке.", show_alert=True)
    else:
        await callback.answer(f"Доступ убран: {info.get('name') or user_id}")
        try:
            await bot.send_message(user_id, "🔒 Ваш доступ к боту закрыт администратором.")
        except Exception as e:
            logger.warning("Не удалось уведомить %s об отзыве доступа: %s", user_id, e)

    text, keyboard = users_list_view()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
