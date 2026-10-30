"""Оформление карточки заказа для уведомления (макет согласован 28.10)."""
from __future__ import annotations

from typing import Optional

from calc import CalcResult
from order_parser import Order


def _place(raw: str) -> str:
    return raw.capitalize() if raw.isupper() else raw


def _money(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def _groups_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "группа"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "группы"
    return "групп"


def format_calc(res: Optional[CalcResult], o: Order) -> str:
    """Строки 11 и 12: расчёт по калькулятору и разница с ценой заказа."""
    if res is None:
        return "🧮 Считаю…\n📊 Разница: считаю…"
    if not res.ok:
        return f"🧮 Расчёт невозможен: {res.reason}\n📊 Разница: расчёт невозможен"
    line = f"🧮 Калькулятор ({res.tariff}): {_money(res.calc_price)} ₽ · {res.km:.0f} км"
    if res.km_source == "км из заказа":
        line += " (км из заказа)"
    if res.urgent and res.urgent_pct:
        line += f", срочная +{res.urgent_pct}%"
    line += ", без платных дорог"
    if res.diff is not None:
        pct = res.diff / res.calc_price * 100 if res.calc_price else 0
        if abs(pct) < 1:
            line += f"\n📊 Разница: ⚪ {'+' if res.diff >= 0 else '−'}{_money(abs(res.diff))} ₽ (≈0%, цена совпала)"
        else:
            sign = "🟢 +" if res.diff >= 0 else "🔴 −"
            line += f"\n📊 Разница: {sign}{_money(abs(res.diff))} ₽ ({pct:+.0f}%)"
    else:
        line += "\n📊 Разница: -"
    return line


def format_card(o: Order, dispatcher: str, group: str,
                calc: Optional[CalcResult] = None, extra_groups: int = 0,
                calc_error: Optional[str] = None) -> str:
    """Все строки показываются; если данных нет, ставится «-» (решение 30.10)."""
    head = "🆕 ЗАКАЗ"
    if o.urgent:
        head += " · ⚡️ СРОЧНО"
    head += f" · {o.time_text}" if o.time_text else " · -"
    lines = [head]

    if o.route_confidence == "none":
        lines.append("📍 -")
        lines.append("🗺️ -")
    else:
        lines.append(f"📍 {_place(o.from_raw)}")
        lines.append(f"🗺️ {_place(o.to_raw)}")

    lines.append(f"👥 {o.passengers} чел" if o.passengers else "👥 -")
    if o.price:
        price = f"💰 {_money(o.price)} ₽"
        if o.price_kind:
            price += f" ({o.price_kind})"
        lines.append(price)
    else:
        lines.append("💰 -")

    if o.tolls == "extra":
        lines.append("🛣 + платные дороги сверху")
    elif o.tolls == "client":
        lines.append("🛣 платные дороги оплачивает клиент")
    elif o.tolls == "mentioned":
        lines.append("🛣 платные дороги упомянуты")
    else:
        lines.append("🛣 -")

    fee = []
    if o.percent:
        fee.append(f"{o.percent}%")
    if o.commission_rub:
        fee.append(f"{_money(o.commission_rub)} ₽")
    lines.append("📌 Комиссия: " + (" · ".join(fee) if fee else "-"))

    lines.append(f"🚗 Класс: {o.car_class}" if o.car_class else "🚗 Класс: -")
    if calc_error or (calc is not None and not calc.ok):
        # км из заказа показываются только когда расчёта нет (при расчёте км уже в строке 11)
        lines.append(f"📏 {o.distance_km} км" if o.distance_km else "📏 -")
    lines.append(f"ℹ️ {o.comment}" if o.comment else "ℹ️ -")

    if calc_error:
        lines.append(f"🧮 Расчёт невозможен: {calc_error}\n📊 Разница: расчёт невозможен")
    else:
        lines.append(format_calc(calc, o))
    lines.append(f"👤 Диспетчер: {dispatcher}")
    grp = f"👥 Группа: {group}"
    if extra_groups:
        grp += f" (+{extra_groups} {_groups_word(extra_groups)})"
    lines.append(grp)

    if o.route_confidence != "none" and (o.route_confidence == "low" or o.address_flag):
        lines.append("⚠️ Маршрут определён неуверенно, проверьте по источнику")
    return "\n".join(lines)
