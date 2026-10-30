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
    r"\s*(?:\u27a1\ufe0f?|\u2b95|\u279c|\u2794|\u21d2|\u2192|=>|-{1,2}>|[—–]>|>{2,3})\s*"
)
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF"
    "\uFE0F\u200d\u203c\u2049]+"
)

CLOCK = r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)"
DATE_NUM = r"(?<!\d)\d{1,2}\.(?:0?[1-9]|1[0-2])(?:\.\d{2,4})?\.?(?!\d)"
DATE_TXT = rf"(?<!\d)\d{{1,2}}\s+{MONTHS}(?:\s+\d{{4}})?"
REL1 = r"через\s+\d+(?:[.,]\d+)?\s*(?:мин\w*|час\w*)"
REL0 = r"через\s+(?:пару\s+час\w*|полчаса|час(?!\w))"
REL2 = r"\+\s*\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s*час\w*"
PASS = r"(?:\d+|один|одна|два|две|три|четыре|пять)[ \t]*(?:чел\w*|пасс\w*|взр\w*)\.?"
LUGG = r"(?:\d+|один|одна|два|две|три|четыре|пять)[ \t]*(?:сумк\w*|багаж\w*|чемодан\w*|мест\w*)"
KM = r"\d+[ \t]*км"
PERCENT = r"/?\s*\d{1,2}\s*%"
CLOCK_PREP = r"(?:(?<!\w)(?:в|к|около|с|до)\s+)?" + CLOCK
EQUATION = r"\d+\s*[*хx×]\s*\d+\s*=\s*[\d ]+"                       # 155*27=4 185
COMM_WORD = r"(?<!\w)(?:комса|комис\w*|ком)(?!\w)\s*[:\-]?\s*\d{1,5}\s*%?"   # Комса 2000, комиссия 10%, ком 500
COMMISSION = r"(?<=\d{3})\s*/\s*\d{1,4}(?:\s*%)?"            # 3000/500, 5800/10, 5.500/10%
THOUSANDS = r"(?<![\d.,])(\d{1,3}(?:[.,]\d)?)\s*(?:тыс|тр|т)(?!\w)\.?"   # 8т, 8 тыс
PRICE_NUM = r"(?<![\d.,])(\d{1,3}(?:[ .]\d{3})+|\d{3,6})(?!\d)"
PHONE = r"(?<!\d)\+?\d[\d\- ()]{9,}\d(?!\d)"

EXTRACT_TOKENS = [EQUATION, COMM_WORD, REL2, REL1, REL0, DATE_TXT, DATE_NUM, CLOCK_PREP, KM, PASS, LUGG, COMMISSION, PERCENT, THOUSANDS, PRICE_NUM]

NOISE = [
    r"пишем\s+(?:я\s+и\s+)?время\s+подачи",
    r"пишем\s+я(?!\w)",
    r"пиш(?:ите|и)\s+(?:я\s+и\s+)?время\s+подачи",
    r"(?<!\w)(?:в\s+)?(?:личк\w*|лс)(?!\w)",
    r"через\s+(?:банкомат|сбп|карт\w*|терминал)",
    r"ждет\s+\d+(?:\s*/\s*\d+)?\s*мин\w*",
    r"(?<!\w)по\s+\d+(?:[.,]\d+)?(?!\w)",
    r"(?<!\w)ближайш\w+\s+(?:авто|машин\w*)(?!\w)",
    r"(?:нужен\s+)?(?<!\w)бустер\w*",
    r"(?<!\w)багаж\w*",
    r"(?<!\w)выезд(?!\w)",
    r"\+\s*\d+\s*мин\w*",
    r"(?<![\w-])т(?![\w-])",
    r"\(?\s*платк\w*\s+в\s+(?:сумме|цене)\s*\)?",
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
    r"платк\w*\s*[:\-]?\s*клиент\w*",
    r"\+?\s*платк\w*",
    r"платн\w+\s+дорог\w*",
    r"с\s+предоплатой",
    r"ручн\w+\s+клад\w+",
    r"перейти\s+к\s+заказу",
    r"(?<!\w)источники?(?!\w)",
    r"(?<!\w)(?:ночью|утром|днём|днем|вечером)(?!\w)",
    r"(?<!\w)(?:ехать|едем|поехать)\s+(?:на|в|до)(?!\w)",
    r"\d+\s*адрес\w*",
    r"(?<!\w)(?:понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)(?!\w)",
    r"(?:\d+\s*)?(?:детей|дети|ребёнок|ребенок|ребёнка|ребенка)(?:\s+\d+(?:\s*и\s*\d+)?\s*(?:лет|года|год))?",
    r"\d+\s*(?:лет|года|год)(?!\w)",
    r"\d+\s*дам\w*",
    r"\+?\s*бейб\w*",
    r"детск\w+\s+кресл\w+(?:\s+обязательн\w+)?",
    r"связь\s+через\s+\w+",
    r"камри.*$",
    r"(?<!\w)(?:иномарк\w*|лифбек|седан|кроссовер|универсал|хэтчбек|внедорожник)(?!\w)",
    r"(?<!\w)(?:машина|доставка|такси)(?!\w)",
    r"(?<!\w)(?:текущ\w*|ближ\w*\s*врем\w*|ближайш\w+\s+врем\w*)(?!\w)",
    r"(?<!\w)пред(?:в\w*)?(?!\w)",
    r"с\s+адрес\w*",
    r"(?<!\w)водител\w*",
    r"(?<!\w)(?:комфорт\s*\+|стандарт|комфорт|минивэн|минивен|эконом|бизнес|вип|vip)(?!\w)",
]

STOP_RE = re.compile(r"план\s+работы|по\s+заказу\s+пока\s+стоп|возьму\s+заказ|(?<!\w)стоп(?!\w)", re.I)

LABELS = {
    "откуда": "from", "а": "from", "куда": "to", "б": "to",
    "сумма водителю": "price", "стоимость": "price", "стоимость поездки": "price", "цена поездки": "price", "цена": "price",
    "оплата": "price", "сумма": "price",
    "дата/время поездки": "time", "когда": "time", "дата": "time", "время": "time",
    "класс авто": "class", "класс": "class", "тариф": "tariff",
    "дополнительная информация": "comment", "комментарии": "comment",
    "комментарий": "comment", "номер заявки": "id",
}
LABEL_RE = re.compile(r"^([A-Za-zА-Яа-яЁё/ ]{1,30}?)\s*:\s*(.*)$")

FOOTER_RE = re.compile(
    r"можно\s+работать|полная\s+информация|если\s+вы\s+не\s+можете|нажмите|подписк|администратор|"
    r"бот\s+по\s+поиску|контакт\s+диспетчера|по\s+кнопке|@\w+|реклам|перейти\s+к\s+заказу", re.I)
REGION_HEADER_RE = re.compile(
    r"^[\w-]+(?:ский|ская|кая|ной)\s+(?:край|обл\.?|область)$|^(?:республика|респ\.?)\s+[\w-]+$", re.I)
PREP_ONLY = {"до", "в", "из", "от", "на", "во", "с", "со", "→"}
ADDR_CUT_RE = re.compile(
    r"\s+(?:ул\.?|улица|пр-т|проспект|пер\.?|переулок|шоссе|наб\.?|набережная|бульвар|б-р|мкр\.?|микрорайон|корп\.?|кв\.?|дом)(?!\w)"
    r"|\s+д\.?\s*\d", re.I)
ADDRISH_RE = re.compile(
    r"(?<!\w)(?:аэропорт\w*|вокзал\w*|ул\.?|улица|бульвар|проспект|пр-т|переулок|шоссе|набережная|мкр\.?|микрорайон)(?!\w)",
    re.I)
REGION_RE = re.compile(r"обл|респ|край|район|р-н|р-он|округ", re.I)
PLACE_PREFIX_RE = re.compile(
    r"^(?:кпп|пгт|гор|г|город|с|п|пос|посёлок|поселок|ст-ца|станица|х|хутор|д|дер|деревня)\.?[\s,]+",
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
    tolls: Optional[str]           # "extra" (+платка) | "included" (в цене) | "client" | "mentioned" | None
    percent: Optional[int]
    urgent: bool
    time_text: Optional[str]
    passengers: Optional[int]
    car_class: Optional[str]
    distance_km: Optional[int]
    comment: Optional[str]
    route_confidence: str          # "high" | "medium" | "low" | "none"
    raw_text: str
    commission_rub: Optional[int] = None   # «3000/500»: число после слэша, если это рубли
    dispatcher: Optional[str] = None       # диспетчер, указанный в тексте заказа
    dispatcher_username: Optional[str] = None
    address_flag: bool = False             # в маршруте адрес (улица, дом, микрорайон) вместо города

    def to_dict(self) -> dict:
        return asdict(self)


CONT_WORDS = {"область", "обл", "район", "край", "республика", "респ"}


def _ampm(m) -> str:
    h = int(m.group(1))
    if m.group(2).lower() in ("вечера", "дня") and h < 12:
        h += 12
    return f" {h}:00 "


def normalize(text: str) -> list[str]:
    t = text.replace("\u00a0", " ").replace("\u202f", " ")
    t = ARROW_RE.sub(" → ", t)
    t = EMOJI_RE.sub(" ", t)
    t = re.sub(r"(?<!\d)(\d{1,2});([0-5]\d)(?!\d)", r"\1:\2", t)
    t = re.sub(r"(?<![\d:.,])(\d{1,2})[ \t]+:[ \t]*([0-5]\d)(?!\d)", r"\1:\2", t)
    t = re.sub(r"(?<![\d,.])(\d{1,2}),([0-5]\d)(?!\d)", r"\1:\2", t)
    t = re.sub(r"(?<![\d:.])(\d{1,2})\s*(утра|ночи|вечера|дня)(?!\w)", _ampm, t, flags=re.I)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    merged: list[str] = []
    for ln in (ln for ln in lines if ln):
        if merged and ln.lower().strip(" .") in CONT_WORDS:
            merged[-1] += " " + ln
        else:
            merged.append(ln)
    return merged


def _remove(text: str, patterns: list[str]) -> str:
    for p in patterns:
        text = re.sub(p, " ; ", text, flags=re.I)
    return text


def _to_int(s: str) -> int:
    return int(re.sub(r"[ .]", "", s))


def extract_price(text: str) -> tuple[Optional[int], Optional[str]]:
    t = _remove(text, [r"https?://\S+", r"#\S+", r"№\s*\d+", PHONE, EQUATION, COMM_WORD])
    t = _remove(t, [DATE_TXT, DATE_NUM, REL1, REL2, CLOCK_PREP, KM, PASS, LUGG, COMMISSION, PERCENT])
    cands = []
    for m in re.finditer(PRICE_NUM, t):
        v = _to_int(m.group(1))
        if 500 <= v <= 500000:
            cands.append((v, t[m.end():m.end() + 14]))
    if not cands:
        th = re.search(THOUSANDS, t, re.I)
        if th:
            cands = [(int(round(float(th.group(1).replace(",", ".")) * 1000)), "")]
        else:
            sh = re.search(r"(?<![\d.,])(\d{1,2})[ \t]*(?:₽|р(?!\w)|руб)", t, re.I)   # «8₽» = 8 000
            if not sh or int(sh.group(1)) < 3:
                return None, None
            cands = [(int(sh.group(1)) * 1000, "")]
    money = re.compile(r"^\s*(?:₽|р(?!\w)|руб|т\.?\s?р|на\s+руки|общ|\+\s*плат)", re.I)
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


def extract_commission(text: str) -> tuple[Optional[int], Optional[int]]:
    """(проценты, рубли) из хвоста вида «3000/500», «5800/10», «5.500/10%»."""
    cw = re.search(COMM_WORD, text, re.I)
    if cw:
        v = int(re.search(r"\d+", cw.group(0)).group(0))
        return (v, None) if "%" in cw.group(0) else (None, v)
    m = re.search(r"(?<=\d{3})\s*/\s*(\d{1,4})(\s*%)?", text)
    if not m:
        return None, None
    v = int(m.group(1))
    if v == 0:
        return None, None
    if m.group(2) or v <= 30:
        return v, None
    return None, v


def extract_dispatcher(lines: list[str]) -> tuple[Optional[str], Optional[str]]:
    """«Диспетчер: @user» или «Диспетчер:» и @user на следующей строке -> (имя, username)."""
    for i, ln in enumerate(lines):
        m = re.match(r"^диспетчер\s*[:\-–—]\s*(.*)$", ln, re.I)
        if not m:
            continue
        val = m.group(1).strip()
        if not val and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if ":" not in nxt and (nxt.startswith("@") or re.fullmatch(r"[\w .-]{2,40}", nxt)):
                val = nxt
        if not val or val.endswith(":"):
            return None, None
        um = re.search(r"@([A-Za-z][A-Za-z0-9_]{3,31})", val)
        username = um.group(1) if um else None
        name = re.sub(r"@[A-Za-z0-9_]+", "", val).strip(" ,.-–—:")
        if name:
            return name, username
        if username:
            return f"@{username}", username
        return None, None
    return None, None


def extract_tolls(text: str) -> Optional[str]:
    if re.search(r"платк\w*\s+в\s+(?:сумме|цене)|платн\w+\s+дорог\w*\s+в\s+(?:сумме|цене)", text, re.I):
        return "included"
    if re.search(r"платк\w*\s*[:\-]?\s*клиент|платн\w+\s+дорог\w+\s+(?:оплачивает\s+)?(?:строго\s+)?клиент|"
                 r"дорог\w+\s+оплачивает\s+(?:строго\s+)?клиент", text, re.I):
        return "client"
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
    if re.search(r"(?<!\w)ночью(?!\w)", text, re.I):
        parts.append("ночью")
    date = re.search(DATE_TXT, text, re.I) or re.search(DATE_NUM, text)
    if date:
        parts.append(date.group(0).strip(" ."))
    clock = re.search(CLOCK, text)
    if clock:
        parts.append(clock.group(0))
    rel = re.search(REL1, text, re.I) or re.search(REL2, text, re.I) or re.search(REL0, text, re.I)
    if rel:
        parts.append(re.sub(r"\s+", " ", rel.group(0)).lower())
    return urgent, (" ".join(parts) if parts else None)


def extract_class(text: str) -> Optional[str]:
    t = text.lower()
    if re.search(r"минивэн|минивен", t):
        return "Минивэн"
    if re.search(r"комфорт\s*(?:\+|плюс)", t):
        return "Комфорт+"
    if "комфорт" in t or re.search(r"камри|camry", t):
        return "Комфорт"
    if re.search(r"стандарт|эконом", t):
        return "Стандарт"
    if "бизнес" in t:
        return "Бизнес"
    return None


PREP_RE = re.compile(r"^(?:из|от|в|во|до)\s+", re.I)
STATION_RE = re.compile(
    r"\s+(?:ж/?д\s+вокзал\w*|жд\s+вокзал\w*|автовокзал\w*|вокзал\w*|аэропорт\w*|аэро|ж/д|жд|посёлок|поселок)$", re.I)


def strip_prep(s: str) -> str:
    return PREP_RE.sub("", s.strip()).strip()


def clean_line(line: str, strip_preps: bool = True) -> str:
    st = line.strip()
    if re.match(r"^\d+\.\s", st) or re.match(r"^такси\s*[\"«“]", st, re.I):
        return ""               # «1. Источник», подпись «Такси "КРУИЗ"»
    if FOOTER_RE.search(st) or re.match(r"^диспетчер", st, re.I):
        return ""               # служебные строки ботов-агрегаторов и «Диспетчер: …»
    if st.startswith("(") and st.rstrip(" .").endswith(")"):
        return ""               # строка целиком в скобках: «(место по согласованию)»
    t = _remove(line, EXTRACT_TOKENS)
    for p in NOISE:
        t = re.sub(p, " ", t, flags=re.I)
    t = re.sub(r"[;…]", " , ", t)
    t = re.sub(r"(?:\s*,\s*){2,}", ", ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:|-–—")
    t = re.sub(r"(?:\s*,)?\s+и\s*$", "", t.strip(" ,.;:|-–—"))     # хвост «…, и» после вырезанных слов
    t = t.lstrip("→ ").strip(" ,.;:|-–—")
    if strip_preps:
        t = strip_prep(t)
    if t.lower() in PREP_ONLY or REGION_HEADER_RE.match(t):
        return ""
    if t.lower() in {"нет", "да"} or len(re.findall(r"[A-Za-zА-Яа-яЁё]", t)) < 2:
        return ""
    return t


def parse_place(raw: str) -> tuple[str, Optional[str]]:
    s = re.sub(r"\s+адрес\s*$", "", strip_prep(raw), flags=re.I).strip(" ,.")
    parts = [x.strip(" .") for x in s.split(",") if x.strip(" .")]
    hint = None
    if len(parts) > 1 and REGION_RE.search(parts[0]):
        # адрес в порядке «регион, район, населённый пункт»
        regions = [x for x in parts if REGION_RE.search(x)]
        rest = [x for x in parts if not REGION_RE.search(x)]
        if rest:
            hint = ", ".join(reversed(regions))
            s = rest[0]
    s = PLACE_PREFIX_RE.sub("", s)
    rm = re.search(r"\s+(ЛНР|ДНР|ХНР|ЗНР)(?!\w)", s, re.I)
    if rm:                                  # «Брянка ЛНР», «Ивановка ЛНР антрацитовский район»
        s = (s[:rm.start()] + s[rm.end():]).strip()
        hint = (hint + ", " if hint else "") + rm.group(1).upper()
    m = re.search(r"\(([^)]*)\)", s)
    if m:
        hint = m.group(1).strip() or hint
        s = (s[:m.start()] + " " + s[m.end():]).strip()
    m = re.search(r"\s+(\S+\s+(?:обл(?:\.|асть)?|край))$", s, re.I)
    if m:
        hint = (hint + ", " if hint else "") + m.group(1)
        s = s[:m.start()].strip()
    m = re.match(r"^(?P<c>[^,()]+?)\s+(?P<h>\S+\s+(?:район|р-н|р-он)\b.*)$", s, re.I)
    if m:                                   # «Развильное песчанокопский район Ростовская область»
        s = m.group("c")
        hint = m.group("h").strip() + (", " + hint if hint else "")
    parts = [x.strip() for x in s.split(",")]
    rest = [x for x in parts[1:] if REGION_RE.search(x)]
    if rest:                                # «Развильное, Песчанокопский район, Ростовская область»
        hint = ", ".join(rest + ([hint] if hint else []))
    city = parts[0].strip(" ,.")
    cut = ADDR_CUT_RE.search(city)
    if cut:
        tail = city[cut.end():]
        city = city[:cut.start()]
        if re.match(r"\s*\d", tail) and " " in city.strip():
            city = city.rsplit(" ", 1)[0]   # «Веселое Стратонавтов улица 24» -> название улицы перед словом «улица»
    pm = re.match(r"^(.+?)\s+(под\s+[А-ЯЁA-Z]\w+)$", city.strip())
    if pm:                                  # «Веселое под Донецком»
        city = pm.group(1)
        hint = (hint + ", " if hint else "") + pm.group(2)
    city = re.sub(r"^(?:аэропорт|аэро|вокзал|ж/?д\s+вокзал|жд)\s+", "", city, flags=re.I)
    city = STATION_RE.sub("", city).strip(" ,.")
    city = PLACE_PREFIX_RE.sub("", city).strip(" ,.") or city
    if city.isupper():
        city = city.capitalize()
    return city, hint


HYPHEN_NAMES = {"санкт петербург", "ростов на дону", "каменск шахтинский", "каменск уральский",
                "ивано франковск", "орехово зуево", "комсомольск на амуре", "гусь хрустальный"}


def norm_hyphen(s: str) -> str:
    return re.sub(r"[-–—\s]+", " ", s.lower().replace("ё", "е")).strip()


def find_route(lines: list[str]) -> tuple[Optional[str], Optional[str], str]:
    for ln in lines:                    # «из А в Б»
        c = clean_line(ln, strip_preps=False)
        m = re.match(r"^(?:из|от|с|со)\s+(.+?)\s+(?:в|во|до)\s+(.+)$", c, re.I)
        if m:
            return m.group(1).strip(), m.group(2).strip(), "high"
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
        parts = re.split(r"\s+[-–—]\s+|\s+-(?=[^\s\d])|(?<=[^\s\d])-\s+|\s*[–—]\s*", c, maxsplit=1)
        if len(parts) == 2 and all(p.strip() for p in parts):
            return strip_prep(parts[0]), strip_prep(parts[1]), "high"
    if len(cl) == 1:                    # «Донецк Ростов», «Донецк-Ростов»: два названия без разделителя
        base = STATION_RE.sub("", cl[0]).strip()
        words = base.split()
        if len(words) == 2 and all(w[:1].isupper() for w in words):
            return words[0], words[1], "low"
        hy = re.fullmatch(r"([А-ЯЁA-Z][\w]+)-([А-ЯЁA-Z][\w]+)", base)
        if hy and norm_hyphen(base) not in HYPHEN_NAMES:
            return hy.group(1), hy.group(2), "low"
    if len(cl) == 4 and ADDRISH_RE.search(cl[1]) and ADDRISH_RE.search(cl[3]) \
            and not ADDRISH_RE.search(cl[0]) and not ADDRISH_RE.search(cl[2]):
        return f"{cl[0]}, {cl[1]}", f"{cl[2]}, {cl[3]}", "medium"   # город и адрес на отдельных строках
    if len(cl) >= 2:
        return cl[0], cl[1], ("medium" if len(cl) == 2 else "low")
    return None, None, "low"


NUM_WORDS = {"один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5}


def _num(token: str) -> int:
    first = token.split()[0].lower().rstrip(".")
    m = re.match(r"\d+", first)
    return int(m.group(0)) if m else NUM_WORDS.get(re.sub(r"[^а-я]", "", first), 1)


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
    passengers = _num(pm.group(0)) if pm else None
    if passengers is None:
        pm3 = re.search(r"пассажир\w*\s*:?\s*(\d+)", full, re.I)
        passengers = int(pm3.group(1)) if pm3 else None
    km = re.search(r"(\d+)\s*км", full, re.I)
    pct, fee_rub = extract_commission(full)
    if pct is None and fee_rub is None:
        pm2 = re.search(r"(\d{1,2})\s*%", full)
        pct = int(pm2.group(1)) if pm2 else None

    if price is None and not time_text and not urgent:
        return None

    comment = labeled.get("comment")
    if not comment:
        extras = []
        for pat in (r"\d+\s*адрес\w*",
                    r"(?:\d+[ \t]*)?(?:детей|дети|ребёнок|ребенок)(?:[ \t]*:[ \t]*\d+)?(?:[ \t]*\(?[ \t]*\d+(?:[ \t]*и[ \t]*\d+)?[ \t]*(?:лет|года|год)[ \t]*\)?)?",
                    r"(?:нужен\s+)?бустер\w*",
                    r"\d+\s*дам\w*\s*\+\s*бейб\w*",
                    r"детск\w+\s+кресл\w+(?:\s+обязательн\w+)?"):
            am = re.search(pat, full, re.I)
            if am:
                extras.append(am.group(0).strip())
        comment = "; ".join(extras) if extras else None
    if comment:
        comment = re.sub(r"\s*\(\s*", " (", comment)
        comment = re.sub(r"\s*\)", ")", comment)
    if comment and len(re.findall(r"[A-Za-zА-Яа-яЁё]", re.sub(PASS, "", comment, flags=re.I))) < 3:
        comment = None

    disp, disp_user = extract_dispatcher(lines)
    addr = bool(from_raw and (ADDR_CUT_RE.search(from_raw.split(",")[0]) or ADDR_CUT_RE.search(to_raw.split(",")[0])))
    from_city, from_hint = parse_place(from_raw)
    to_city, to_hint = parse_place(to_raw)
    return Order(
        from_raw=from_raw, from_city=from_city, from_hint=from_hint,
        to_raw=to_raw, to_city=to_city, to_hint=to_hint,
        price=price, price_kind=kind, tolls=extract_tolls(full),
        percent=pct, commission_rub=fee_rub,
        dispatcher=disp, dispatcher_username=disp_user, address_flag=addr,
        urgent=urgent, time_text=time_text, passengers=passengers,
        car_class=extract_class(labeled.get("class", "") + " " + full),
        distance_km=int(km.group(1)) if km else None,
        comment=comment, route_confidence=conf, raw_text=text,
    )
