"""Оформление карточки заказа для уведомления."""
from __future__ import annotations

from typing import Optional

from order_parser import Order


def _place(raw: str) -> str:
    return raw.capitalize() if raw.isupper() else raw


def _money(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def format_card(o: Order, dispatcher: str, group: str) -> str:
    head = "🆕 ЗАКАЗ"
    if o.urgent:
        head += " · ⚡ СРОЧНО"
    if o.time_text:
        head += f" · {o.time_text}"

    if o.route_confidence == "none":
        excerpt = " ".join(o.raw_text.split())[:300]
        lines = [head, "📍 Маршрут не распознан, смотрите источник", f"📝 {excerpt}"]
    else:
        lines = [head, f"📍 {_place(o.from_raw)} → {_place(o.to_raw)}"]

    money = []
    if o.passengers:
        money.append(f"👥 {o.passengers} чел")
    if o.price:
        p = f"💰 {_money(o.price)} ₽"
        if o.price_kind:
            p += f" ({o.price_kind})"
        money.append(p)
    else:
        money.append("💰 цена не указана")
    lines.append(" · ".join(money))

    if o.tolls == "extra":
        lines.append("🛣 + платные дороги сверху")
    elif o.tolls == "mentioned":
        lines.append("🛣 платные дороги упомянуты")
    if o.percent:
        lines.append(f"📌 в заказе указано {o.percent}%")
    if o.car_class:
        lines.append(f"🚗 Класс: {o.car_class}")
    if o.distance_km:
        lines.append(f"📏 {o.distance_km} км")
    if o.comment:
        lines.append(f"ℹ️ {o.comment}")

    lines.append(f"👤 Диспетчер: {dispatcher}")
    lines.append(f"👥 Группа: {group}")
    if o.route_confidence in ("medium", "low"):
        lines.append("⚠️ Маршрут определён неуверенно, проверьте по источнику")
    return "\n".join(lines)
