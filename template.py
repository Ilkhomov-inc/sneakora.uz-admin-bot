from dataclasses import dataclass
from typing import Optional
from config import config


@dataclass
class SneakerData:
    brand: str
    model: str
    gender_type: str = "Унисекс"  # Женская / Мужская / Унисекс
    sizes: str = "Все размеры"
    colors: str = "Оригинальный"
    price: Optional[str] = None
    notes: Optional[str] = None


def format_sneaker_post(
    data: SneakerData,
    custom_price: Optional[str] = None,
    price_mode: Optional[str] = None,
) -> str:
    """
    Форматирует характеристики кроссовок по утвержденному шаблону SNEAKORA.
    """
    mode = price_mode or config.PRICE_MODE
    brand_upper = (data.brand or "SNEAKERS").strip().upper()
    model_name = (data.model or "Оригинал").strip()
    gender = (data.gender_type or "Унисекс").strip()
    sizes = (data.sizes or config.DEFAULT_SIZES).strip()
    colors = (data.colors or "Стандартный").strip()

    # Точка в конце цветов, если её нет
    if colors and not colors.endswith("."):
        colors += "."

    # Обработка цены
    price_val = custom_price if custom_price is not None else data.price

    price_line = ""
    if price_val:
        # Если пользователь или ИИ передали цену
        formatted_price = price_val.strip()
        if not (formatted_price.endswith("$") or formatted_price.endswith("₽") or "руб" in formatted_price.lower()):
            formatted_price = f"{formatted_price}$"
        price_line = f"💰 Цена: {formatted_price}\n"
    elif mode == "placeholder":
        price_line = "💰 Цена: ___$\n"
    elif mode == "omit":
        price_line = ""
    else:
        price_line = "💰 Цена: ___$\n"

    # Сборка финального шаблона
    post = (
        f"👟 {brand_upper} | НОВАЯ КОЛЛЕКЦИЯ\n\n"
        f"🔥 Стиль и комфорт в каждом шаге!\n\n"
        f"✨ Характеристики:\n"
        f"▫️ Модель: {model_name}\n"
        f"▫️ Тип: {gender}\n"
        f"▫️ Размеры: {sizes}\n"
        f"▫️ Цвет: {colors}\n"
        f"{price_line}\n"
        f"🛍 Обнови свой стиль вместе со {config.SHOP_NAME}!\n\n"
        f"📩 Для заказа: пиши в личные сообщения.\n\n"
        f"⚡ Успей заказать свою пару!\n\n"
        f"{config.ADMIN_HANDLE}"
    )

    # Убираем лишние двойные переносы строк, если строка цены была пустой
    while "\n\n\n" in post:
        post = post.replace("\n\n\n", "\n\n")

    return post.strip()
