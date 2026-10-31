"""Автоприём заказа: выбор способа, текст сообщения диспетчеру, поиск кнопки «Взять»."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from cards import _money, _place
from order_parser import Order

TAKE_BUTTON_RE = re.compile(r"взять|запрос|принять|беру|забрать|взял", re.I)
DM_WORDS_RE = re.compile(r"в\s+личк\w*|в\s+лс(?!\w)|(?<!\w)лс(?!\w)|в\s+личные|в\s+директ|в\s+(?:л/с|ls)", re.I)


def wants_dm(text: str) -> bool:
    """В тексте заказа просят писать диспетчеру лично."""
    return bool(DM_WORDS_RE.search(text or ""))


def is_dm_only(chat_id: int, username: Optional[str], exceptions: list) -> bool:
    """Группа из исключений: «Я» писать нельзя, только диспетчеру. В списке имена (без @) и id."""
    ex = {str(x).strip().lower().lstrip("@") for x in exceptions}
    return str(chat_id) in ex or bool(username) and username.lower() in ex


def find_take_button(rows) -> Optional[tuple[int, int, object]]:
    """Первая кнопка вида «Взять заказ» / «Запросить» под сообщением -> (строка, столбец, кнопка)."""
    for i, row in enumerate(rows or []):
        for j, b in enumerate(row):
            if TAKE_BUTTON_RE.search(getattr(b, "text", "") or ""):
                return i, j, b
    return None


def dm_text(o: Order) -> str:
    parts = []
    if o.from_raw and o.to_raw:
        parts.append(f"{_place(o.from_raw)} → {_place(o.to_raw)}")
    if o.time_text:
        parts.append(o.time_text)
    elif o.urgent:
        parts.append("срочно")
    if o.price:
        parts.append(f"{_money(o.price)} ₽")
    return "Здравствуйте! Беру заказ" + (": " + ", ".join(parts) if parts else "") + "."


def dm_url(username: str, o: Order) -> str:
    """Ссылка, которая открывает чат с диспетчером и вставляет текст в поле ввода."""
    return f"https://t.me/{username.lstrip('@')}?text={quote(dm_text(o))}"
