"""Правиловый парсер заказов трансфера из свободного текста (этап 1).

parse_order(text) -> Order | None
None означает «это не заказ» (чат, реклама, план работы и т.п.).
Если расчёт невозможен (нет цены/точек), заказ всё равно возвращается,
а бот покажет пометку «расчёт невозможен».
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

MONTHS = r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"

ARROW_RE = re.compile(
    r"\s*(?:\u27a1\ufe0f?|\u2b95|\u279c|\u2794|\u21d2|\u2192|=>|-{1,2}>|[—–]>)\s*"
)
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF"
    "\uFE0F\u200d\u203c\u2049]+"
)

CLOCK = r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)"
DATE_NUM = r"(?<!\d)\d{1,2}\.(?:0?[1-9]|1[0-2])(?:\.\d{2,4})?\.?(?!\d)"
DATE_TXT = rf"(?<!\d)\d{{1,2}}\s+{MONTHS}(?:\s+\d{{4}})?"
REL1 = r"через\s+\d+(?:[.,]\d+)?\s*(?:мин\w*|час\w*)"
REL2 = r"\+\s*\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s*час\w*"
PASS = r"\d+\s*(?:чел\w*|пасс\w*)\.?"
LUGG = r"\d+\s*(?:сумк\w*|багаж\w*|чемодан\w*|мест\w*)"
KM = r"\d+\s*км"
PERCENT = r"/?\s*\d{1,2}\s*%"
PRICE_NUM = r"(?<![\d.,])(\d{1,3}(?:[ .]\d{3})+|\d{3,6})(?!\d)"
PHONE = r"(?<!\d)\+?\d[\d\- ()]{9,}\d(?!\d)"

EXTRACT_TOKENS = [REL2, REL1, DATE_TXT, DATE_NUM, CLOCK, KM, PASS, LUGG, PERCENT, PRICE_NUM]

NOISE = [
    r"пишем\s+время\s+подачи",
    r"ждут\s+с\s+\w+",
    r"желательно\s+\w+",
    r"взять\s+заказ",
    r"запросить",
    r"на\s+руки",
    r"(?<!\w)общ(?:ее|ая|ий)(?!\w)",
    r"(?<!\w)(?:сейчас|срочно|сегодня|завтра|послезавтра)(?!\w)",
    r"(?<!\w)заказ(?!\w)",
    r"выбор\s+авто",
    r"₽",
    r"(?<![\w-])р(?:уб)?\.?(?![\w-])",
    r"\+?\s*платк\w*",
    r"платн\w+\s+дорог\w*",
    r"с\s+предоплатой",
    r"\d+\s*адрес\w*",
    r"(?<!\w)водител\w*",
    r"(?<!\w)(?:комфорт\s*\+|стандарт|комфорт|минивэн|минивен|эконом|бизнес|вип|vip)(?!\w)",
]

STOP_RE = re.compile(r"план\s+работы|по\s+заказу\s+пока\s+стоп|возьму\s+заказ|(?<!\w)стоп(?!\w)", re.I)

LABELS = {
    "откуда": "from", "а": "from", "куда": "to", "б": "to",
    "сумма водителю": "price", "стоимость": "price", "цена": "price",
    "оплата": "price", "сумма": "price",
    "дата/время поездки": "time", "когда": "time", "дата": "time", "время": "time",
    "класс авто": "class", "класс": "class", "тариф": "tariff",
    "дополнительная информация": "comment", "комментарии": "comment",
    "комментарий": "comment", "номер заявки": "id",
}
LABEL_RE = re.compile(r"^([A-Za-zА-Яа-яЁё/ ]{1,30}?)\s*:\s*(.*)$")

PLACE_PREFIX_RE = re.compile(
    r"^(?:пгт|гор|г|город|с|п|пос|посёлок|поселок|ст-ца|станица|х|хутор|д|дер|деревня)\.?[\s,]+",
    re.I,
)


@dataclass
class Order:
    from_raw: str
    from_city: str
    from_hint: Optional[str]
    to_raw: str
    to_city: str
    to_hint: Optional[str]
    price: Optional[int]
    price_kind: Optional[str]      # "на руки" | "общее" | "водителю" | None
    tolls: Optional[str]           # "extra" (+платка) | "mentioned" | None
    percent: Optional[int]
    urgent: bool
    time_text: Optional[str]
    passengers: Optional[int]
    car_class: Optional[str]
    distance_km: Optional[int]
    comment: Optional[str]
    route_confidence: str          # "high" | "medium" | "low"
    raw_text: str

    def to_dict(self) -> dict:
        return asdict(self)


def normalize(text: str) -> list[str]:
    t = text.replace("\u00a0", " ").replace("\u202f", " ")
    t = ARROW_RE.sub(" → ", t)
    t = EMOJI_RE.sub(" ", t)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    return [ln for ln in lines if ln]


def _remove(text: str, patterns: list[str]) -> str:
    for p in patterns:
        text = re.sub(p, " ; ", text, flags=re.I)
    return text


def _to_int(s: str) -> int:
    return int(re.sub(r"[ .]", "", s))


def extract_price(text: str) -> tuple[Optional[int], Optional[str]]:
    t = _remove(text, [r"https?://\S+", r"#\S+", r"№\s*\d+", PHONE])
    t = _remove(t, [DATE_TXT, DATE_NUM, REL1, REL2, CLOCK, KM, PASS, LUGG, PERCENT])
    cands = []
    for m in re.finditer(PRICE_NUM, t):
        v = _to_int(m.group(1))
        if 500 <= v <= 500000:
            cands.append((v, t[m.end():m.end() + 14]))
    if not cands:
        return None, None
    money = re.compile(r"^\s*(?:₽|р(?!\w)|руб|т\.?\s?р|на\s+руки|общ)", re.I)
    adj = [c for c in cands if money.match(c[1])]
    price = (adj[0] if adj else cands[-1])[0]
    kind = None
    if re.search(r"на\s+руки", text, re.I):
        kind = "на руки"
    elif re.search(r"общ(?:ее|ая|ий)", text, re.I):
        kind = "общее"
    elif re.search(r"водител", text, re.I):
        kind = "водителю"
    return price, kind


def extract_tolls(text: str) -> Optional[str]:
    if re.search(r"\+\s*платк|\+\s*платн", text, re.I):
        return "extra"
    if re.search(r"платк|платн", text, re.I):
        return "mentioned"
    return None


def extract_time(text: str) -> tuple[bool, Optional[str]]:
    urgent = bool(re.search(r"(?<!\w)(?:сейчас|срочно)(?!\w)", text, re.I))
    parts = []
    day = re.search(r"(?<!\w)(сегодня|завтра|послезавтра)(?!\w)", text, re.I)
    if day:
        parts.append(day.group(1).lower())
    date = re.search(DATE_TXT, text, re.I) or re.search(DATE_NUM, text)
    if date:
        parts.append(date.group(0).strip(" ."))
    clock = re.search(CLOCK, text)
    if clock:
        parts.append(clock.group(0))
    rel = re.search(REL1, text, re.I) or re.search(REL2, text, re.I)
    if rel:
        parts.append(re.sub(r"\s+", " ", rel.group(0)))
    return urgent, (" ".join(parts) if parts else None)


def extract_class(text: str) -> Optional[str]:
    t = text.lower()
    if re.search(r"минивэн|минивен", t):
        return "Минивэн"
    if re.search(r"комфорт\s*(?:\+|плюс)", t):
        return "Комфорт+"
    if "комфорт" in t:
        return "Комфорт"
    if re.search(r"стандарт|эконом", t):
        return "Стандарт"
    if "бизнес" in t:
        return "Бизнес"
    return None


PREP_RE = re.compile(r"^(?:из|от|в|во|до)\s+", re.I)
STATION_RE = re.compile(
    r"\s+(?:ж/?д\s+вокзал\w*|жд\s+вокзал\w*|автовокзал\w*|вокзал\w*|аэропорт\w*|ж/д)$", re.I)


def strip_prep(s: str) -> str:
    return PREP_RE.sub("", s.strip()).strip()


def clean_line(line: str) -> str:
    t = _remove(line, EXTRACT_TOKENS)
    for p in NOISE:
        t = re.sub(p, " ", t, flags=re.I)
    t = re.sub(r"[;…]", " , ", t)
    t = re.sub(r"(?:\s*,\s*){2,}", ", ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:|-–—")
    t = strip_prep(t)
    if t.lower() in {"нет", "да"} or len(re.findall(r"[A-Za-zА-Яа-яЁё]", t)) < 2:
        return ""
    return t


def parse_place(raw: str) -> tuple[str, Optional[str]]:
    s = re.sub(r"\s+адрес\s*$", "", strip_prep(raw), flags=re.I).strip(" ,.")
    s = PLACE_PREFIX_RE.sub("", s)
    hint = None
    m = re.search(r"\(([^)]*)\)", s)
    if m:
        hint = m.group(1).strip() or None
        s = (s[:m.start()] + " " + s[m.end():]).strip()
    m = re.search(r"\s+(\S+\s+обл(?:\.|асть)?)$", s, re.I)
    if m:
        hint = hint or m.group(1)
        s = s[:m.start()].strip()
    city = STATION_RE.sub("", s.split(",")[0].strip(" ,.")).strip(" ,.")
    if city.isupper():
        city = city.capitalize()
    return city, hint


def find_route(lines: list[str]) -> tuple[Optional[str], Optional[str], str]:
    cl = [c for c in (clean_line(ln) for ln in lines) if c]
    for i, c in enumerate(cl):
        if "→" in c:
            left, right = (strip_prep(p.strip(" ,.-–—")) for p in c.split("→", 1))
            if not left and i > 0:
                left = cl[i - 1]
            if not right and i + 1 < len(cl):
                right = cl[i + 1]
            if left and right:
                return left, right, "high"
    for c in cl:
        parts = re.split(r"\s+[-–—]\s+|\s*[–—]\s*", c, maxsplit=1)
        if len(parts) == 2 and all(p.strip() for p in parts):
            return strip_prep(parts[0]), strip_prep(parts[1]), "high"
    if len(cl) >= 2:
        return cl[0], cl[1], ("medium" if len(cl) == 2 else "low")
    return None, None, "low"


def parse_order(text: str, allow_unrouted: bool = False) -> Optional[Order]:
    if not text or len(text) > 1500 or STOP_RE.search(text):
        return None
    lines = normalize(text)

    labeled: dict[str, str] = {}
    body: list[str] = []
    for ln in lines:
        m = LABEL_RE.match(ln)
        key = LABELS.get(m.group(1).strip().lower()) if m else None
        if key:
            labeled.setdefault(key, m.group(2).strip())
            if m.group(1).strip().lower() == "сумма водителю":
                labeled["price_kind"] = "водителю"
        else:
            body.append(ln)

    if labeled.get("from") and labeled.get("to"):
        from_raw, to_raw, conf = labeled["from"], labeled["to"], "high"
    else:
        from_raw, to_raw, conf = find_route(body)
    if not from_raw or not to_raw:
        if not allow_unrouted:
            return None
        from_raw = to_raw = ""
        conf = "none"

    full = "\n".join(lines)
    price, kind = extract_price(labeled["price"]) if labeled.get("price") else (None, None)
    if price is None:
        price, kind = extract_price("\n".join(body))
    kind = labeled.get("price_kind") or kind

    urgent, time_text = extract_time(labeled.get("time", "") + "\n" + "\n".join(body))
    pm = re.search(PASS, full, re.I)
    passengers = int(re.match(r"\d+", pm.group(0)).group(0)) if pm else None
    km = re.search(r"(\d+)\s*км", full, re.I)
    pct = re.search(r"(\d{1,2})\s*%", full)

    if price is None and not time_text and not urgent:
        return None

    comment = labeled.get("comment")
    if not comment:
        am = re.search(r"\d+\s*адрес\w*", full, re.I)
        comment = am.group(0) if am else None
    if comment and len(re.findall(r"[A-Za-zА-Яа-яЁё]", re.sub(PASS, "", comment, flags=re.I))) < 3:
        comment = None

    from_city, from_hint = parse_place(from_raw)
    to_city, to_hint = parse_place(to_raw)
    return Order(
        from_raw=from_raw, from_city=from_city, from_hint=from_hint,
        to_raw=to_raw, to_city=to_city, to_hint=to_hint,
        price=price, price_kind=kind, tolls=extract_tolls(full),
        percent=int(pct.group(1)) if pct else None,
        urgent=urgent, time_text=time_text, passengers=passengers,
        car_class=extract_class(labeled.get("class", "") + " " + full),
        distance_km=int(km.group(1)) if km else None,
        comment=comment, route_confidence=conf, raw_text=text,
    )
