"""Фильтры заказов по настройкам. passes() -> (прошёл, причина отказа)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Optional

from order_parser import CLOCK, DATE_NUM, DATE_TXT, ROSTOV_RE, Order
from settings import Settings

MONTH_NUM = {m: i + 1 for i, m in enumerate(
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split())}


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[-–—.,()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


ROSTOV_N = "ростов на дону"
ROSTOV_TEXT = r"(?<!\w)ростов(?:а|е|у|ом)?(?!\w)(?!\s+великий)"


def _wanted(wanted: list[str]) -> list[str]:
    """Любой вариант Ростова в настройках = Ростов-на-Дону (а не «Ростовская область»)."""
    return [ROSTOV_N if ROSTOV_RE.match(norm(w)) else norm(w) for w in wanted if norm(w)]


def city_match(candidates: list[str], wanted: list[str]) -> bool:
    ws = _wanted(wanted)
    if not ws:
        return True
    for raw in candidates:
        n = norm(raw)
        if not n:
            continue
        for w in ws:
            if n == w or n.startswith(w + " "):
                return True
            stem = w[:-1] if w[-1] in "аяьиеуо" else w      # Москва -> москв (Москвы, Москве)
            if " " not in w and len(w) >= 5 and n.split()[0].startswith(stem):
                return True
    return False


def _stem_pattern(w: str) -> str:
    if " " in w or len(w) < 5:
        return r"(?<!\w)" + re.escape(w) + r"(?!\w)"
    return r"(?<!\w)" + re.escape(w[:-1])      # основа слова: Москва, Москву, Москвы


ORIGIN_PREPS = {"из", "от", "со", "с"}
DEST_PREPS = {"в", "во", "до", "на", "к"}


def text_has_city(text: str, wanted: list[str], role: Optional[str] = None) -> bool:
    """Город есть в тексте. role="from": не считаем упоминания после «в/до/на»; role="to": после «из/от/с»."""
    ws = _wanted(wanted)
    if not ws:
        return True
    t = norm(text)
    skip = DEST_PREPS if role == "from" else ORIGIN_PREPS if role == "to" else set()
    for w in ws:
        for m in re.finditer(ROSTOV_TEXT if w == ROSTOV_N else _stem_pattern(w), t):
            prev = t[:m.start()].split()[-1:]
            if not prev or prev[0] not in skip:
                return True
    return False


def merge_cities(current: list[str], text: str) -> list[str]:
    """Список пополняется: новые города добавляются, «-Город» удаляет, «-» очищает весь список."""
    t = text.strip()
    if t.lower() in {"-", "–", "—", "0", "нет", "сброс"}:
        return []
    result = list(current)
    for item in re.split(r"[,;\n]", t):
        item = item.strip()
        if not item:
            continue
        if item[0] in "-–—" and item.lstrip("-–— ").strip():
            name = norm(item.lstrip("-–— "))
            result = [c for c in result if norm(c) != name]
        elif norm(item) and norm(item) not in {norm(c) for c in result}:
            result.append(item)
    return result


def pickup_datetime(o: Order, now: datetime) -> Optional[datetime]:
    """Когда подача. None, если время определить нельзя."""
    if o.urgent:
        return now
    t = o.time_text or ""
    m = re.search(r"через\s+(\d+(?:[.,]\d+)?)\s*(мин\w*|час\w*)", t, re.I)
    if m:
        v = float(m.group(1).replace(",", "."))
        return now + timedelta(minutes=v if m.group(2).lower().startswith("мин") else v * 60)
    m0 = re.search(r"(?:через\s+(пару\s+час\w*|полчаса|час(?!\w))|в\s+(течение\s+часа))", t, re.I)
    if m0:
        w = (m0.group(1) or m0.group(2)).lower()
        return now + timedelta(hours=2 if w.startswith("пару") else 0.5 if w.startswith("полчаса") else 1)
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
            dt = datetime.combine(day, time(hh, mm), tzinfo=now.tzinfo)
        else:
            dt = datetime.combine(now.date(), time(hh, mm), tzinfo=now.tzinfo)
            if dt < now - timedelta(minutes=30):
                dt += timedelta(days=1)
        if "ночью" in t.lower() and hh < 6 and dt.date() == now.date() and now.hour >= 12:
            dt += timedelta(days=1)         # «сегодня ночью с 1:00», написано вечером
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
    # Города: из А куда угодно, откуда угодно в Б, и из А в Б (достаточно любого совпадения)
    if s.from_cities or s.to_cities:
        directional = o.route_confidence in ("high", "medium")
        guessed = o.route_confidence == "low" and bool(o.from_city and o.to_city)
        from_c, to_c = [o.from_city, o.from_raw], [o.to_city, o.to_raw]
        from_ok = to_ok = False
        if s.from_cities:
            if directional:
                from_ok = city_match(from_c, s.from_cities)
            else:   # неуверенный маршрут: сначала догадка, затем поиск по тексту без учёта роли «куда»
                from_ok = (guessed and city_match(from_c, s.from_cities)) or (
                    text_has_city(o.raw_text, s.from_cities, "from")
                    and not (guessed and city_match(to_c, s.from_cities)))
        if s.to_cities:
            if directional:
                to_ok = city_match(to_c, s.to_cities)
            else:
                to_ok = (guessed and city_match(to_c, s.to_cities)) or (
                    text_has_city(o.raw_text, s.to_cities, "to")
                    and not (guessed and city_match(from_c, s.to_cities)))
        if not (from_ok or to_ok):
            return False, "города не совпали"
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
