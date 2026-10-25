"""Фильтры заказов по настройкам. passes() -> (прошёл, причина отказа)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Optional

from order_parser import CLOCK, DATE_NUM, DATE_TXT, Order
from settings import Settings

MONTH_NUM = {m: i + 1 for i, m in enumerate(
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split())}


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[-–—.,()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def city_match(candidates: list[str], wanted: list[str]) -> bool:
    ws = [norm(w) for w in wanted if norm(w)]
    if not ws:
        return True
    for raw in candidates:
        n = norm(raw)
        if not n:
            continue
        for w in ws:
            if n == w or n.startswith(w + " "):
                return True
            if " " not in w and len(w) >= 5 and n.split()[0].startswith(w):
                return True
    return False


def _stem_pattern(w: str) -> str:
    if " " in w or len(w) < 5:
        return r"(?<!\w)" + re.escape(w) + r"(?!\w)"
    return r"(?<!\w)" + re.escape(w[:-1])      # основа слова: Москва, Москву, Москвы


def text_has_city(text: str, wanted: list[str]) -> bool:
    ws = [norm(w) for w in wanted if norm(w)]
    if not ws:
        return True
    t = norm(text)
    return any(re.search(_stem_pattern(w), t) for w in ws)


def pickup_datetime(o: Order, now: datetime) -> Optional[datetime]:
    """Когда подача. None, если время определить нельзя."""
    if o.urgent:
        return now
    t = o.time_text or ""
    m = re.search(r"через\s+(\d+(?:[.,]\d+)?)\s*(мин\w*|час\w*)", t, re.I)
    if m:
        v = float(m.group(1).replace(",", "."))
        return now + timedelta(minutes=v if m.group(2).lower().startswith("мин") else v * 60)
    m = re.search(r"\+\s*(\d+(?:[.,]\d+)?)", t)
    if m and "час" in t:
        return now + timedelta(hours=float(m.group(1).replace(",", ".")))
    c = re.search(CLOCK, t)
    if not c:
        return None
    hh, mm = map(int, c.group(0).split(":"))
    try:
        day: Optional[date] = None
        d = re.search(DATE_TXT, t, re.I)
        if d:
            p = d.group(0).split()
            day = date(now.year, MONTH_NUM[p[1].lower()], int(p[0]))
        else:
            dn = re.search(DATE_NUM, t)
            if dn:
                nums = re.findall(r"\d+", dn.group(0))
                day = date(now.year, int(nums[1]), int(nums[0]))
        if day is None:
            w = re.search(r"(сегодня|завтра|послезавтра)", t, re.I)
            if w:
                shift = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[w.group(1).lower()]
                day = now.date() + timedelta(days=shift)
        if day is not None:
            return datetime.combine(day, time(hh, mm), tzinfo=now.tzinfo)
        dt = datetime.combine(now.date(), time(hh, mm), tzinfo=now.tzinfo)
        if dt < now - timedelta(minutes=30):
            dt += timedelta(days=1)
        return dt
    except ValueError:
        return None


def passes(o: Order, s: Settings, now: datetime) -> tuple[bool, str]:
    if not s.enabled:
        return False, "пауза"
    if s.min_price > 0:
        if o.price is None:
            if not s.unknown_ok:
                return False, "нет цены"
        elif o.price < s.min_price:
            return False, "цена ниже минимума"
    directional = o.route_confidence in ("high", "medium")
    if directional:
        from_ok = city_match([o.from_city, o.from_raw], s.from_cities)
        to_ok = city_match([o.to_city, o.to_raw], s.to_cities)
    else:   # маршрут не разобран уверенно: города ищутся просто в тексте
        from_ok = text_has_city(o.raw_text, s.from_cities)
        to_ok = text_has_city(o.raw_text, s.to_cities)
    if not from_ok:
        return False, "город отправления"
    if not to_ok:
        return False, "город назначения"
    if s.time_mode == "urgent":
        if not o.urgent and not (s.unknown_ok and not o.time_text):
            return False, "не срочный"
    elif s.time_mode == "within":
        pt = pickup_datetime(o, now)
        if pt is None:
            if not s.unknown_ok:
                return False, "время неизвестно"
        elif not (now - timedelta(hours=1) <= pt <= now + timedelta(hours=s.time_hours)):
            return False, "время вне окна"
    return True, ""
