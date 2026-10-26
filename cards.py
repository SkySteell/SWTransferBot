"""Оформление карточки заказа для уведомления."""
from __future__ import annotations

from typing import Optional

from calc import CalcResult
from order_parser import Order


def _place(raw: str) -> str:
    return raw.capitalize() if raw.isupper() else raw


def _money(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def format_calc(res: Optional[CalcResult], o: Order) -> str:
    if res is None:
        return "🧮 Считаю…"
    if not res.ok:
        return f"🧮 Расчёт невозможен: {res.reason}"
    line = f"🧮 Калькулятор ({res.tariff}): {_money(res.calc_price)} ₽ · {res.km:.0f} км"
    if res.km_source == "км из заказа":
        line += " (км из заказа)"
    if res.urgent:
        line += f", срочная +{res.urgent_pct}%"
    if res.diff is not None:
        pct = res.diff / res.calc_price * 100 if res.calc_price else 0
        sign = "🟢 +" if res.diff >= 0 else "🔴 −"
        line += f"\n📊 Разница: {sign}{_money(abs(res.diff))} ₽ ({pct:+.0f}%)"
    if o.tolls == "extra":
        line += "\n   (платные дороги не учтены ни в заказе, ни в расчёте)"
    return line


def format_card(o: Order, dispatcher: str, group: str, calc_text: Optional[str] = None) -> str:
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

    if calc_text:
        lines.append(calc_text)
    lines.append(f"👤 Диспетчер: {dispatcher}")
    lines.append(f"👥 Группа: {group}")
    if o.route_confidence in ("medium", "low"):
        lines.append("⚠️ Маршрут определён неуверенно, проверьте по источнику")
    return "\n".join(lines)
