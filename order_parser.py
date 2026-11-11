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

from grammar import CITIES, nominative

MONTHS = r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"

ARROW_RE = re.compile(
    r"\s*(?:\u27a1\ufe0f?|\u2b95|\u279c|\u2794|\u21d2|\u2192|=>|-{1,2}>|[—–]>|>{2,3}|(?<=[^\s>=-])>(?=[^\s>=]))\s*"
)
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF"
    "\uFE0F\u200d\u203c\u2049]+"
)

CLOCK = r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)"
DATE_NUM = r"(?<!\d)\d{1,2}\.(?:0?[1-9]|1[0-2])(?:\.\d{2,4})?\.?(?!\d)"
DATE_TXT = rf"(?<!\d)\d{{1,2}}\s+{MONTHS}(?:\s+\d{{4}})?"
REL1 = r"через\s+\d+(?:[.,]\d+)?\s*(?:мин\w*|час\w*|ч(?!\w))"
REL0 = r"(?:через\s+(?:пару\s+час\w*|полчаса|час(?!\w))|в\s+течение\s+часа)"
REL2 = r"\+\s*\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s*час\w*"
PASS = r"(?:\d+[ \t]*[-–][ \t]*)?(?:\d+|один|одна|два|две|три|четыре|пять)[ \t]*(?:чел\w*|пас{1,2}\w*|взр\w*|(?<=\b[1-9])[ \t]*ч(?!\w)(?:[ \t]*взр\w*)?)\.?"
LUGG = r"(?:\d+|один|одна|два|две|три|четыре|пять)[ \t]*(?:сумк\w*|багаж\w*|чемодан\w*|рюкзак\w*|мест\w*)"
KM = r"\d+[ \t]*км"
PERCENT = r"/?\s*\d{1,2}\s*%"
CLOCK_PREP = r"(?:(?<!\w)(?:в|к|около|с|до)\s+)?" + CLOCK
EQUATION = r"\d+\s*[*хx×]\s*\d+\s*=\s*[\d ]+"                       # 155*27=4 185
COMM_WORD = r"(?<!\w)(?:комса|комис\w*|ком)(?!\w)\s*[:\-]?\s*\d{1,5}\s*%?"   # Комса 2000, комиссия 10%, ком 500
COMMISSION = r"(?<=\d{3})\s*[/:]\s*\d{1,4}(?:\s*%)?"            # 3000/500, 5800/10, 5.500/10%
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
    r"\(\s*кто\s+рядом\s*\)|(?<!\w)кто\s+рядом(?!\w)",
    r"(?<!\w)(?:отвезти|отвести|довезти|доставить|вести|везти)(?!\w)",
    r"(?<!\w)главн\w+(?=\s+(?:жд|ж/д|вокзал|автовокзал))",
    r"±",
    r"(?<!\w)на\s+(?:утро|вечер|день|ночь)(?!\w)",
    r"по\s+заказам\s+писать",
    r"(?:писать\s+)?сюда\s*👉.*",
    r"(?<!\w)сюда\s+междугороднее\s+такси",
    r"(?<!\w)ждут?(?!\w)",
    r"(?<!\w)пер?едварительн\w*\s+заказ",
    r"(?<!\w)(?:собак\w*|собачк\w*)(?!\w)",
    r"(?<!\w)на\s+руках(?!\w)",
    r"кто\s+точно\s+сможет",
    r"только\s+с\s+тем\s+кем\s+работал",
    r"информация\s+от\s*:.*",
    r"нужно\s+забрать(?:\s+и\s+(?:привести|привезти))?(?:\s+в\s+течение\s+дня)?",
    r"(?<!\w)(?:забрать|привезти|привести|маленьк\w+|коробк\w*|пакет\w*|посылк\w*|попутн\w+|набор\s+\w+)(?!\w)",
    r"(?<!\w)док(?:и|ов|ументы?|ументов)(?!\w)",
    r"\s+и\s+(?=(?:в|во|до)\s)",
    r"(?<!\w)(?:спрашивает|кто\s+и\s+сколько)(?!\w)",
    r"(?<!\w)выезд(?!\w)",
    r"(?<!\w)ближайш(?:ему|ий|ая)(?!\w)",
    r"(?<!\w)к\s+сожалению(?!\w)",
    r"(?<!\w)по\s+бесплатк\w*",
    r"(?<!\w)(?:\d+|две|два|три)\s+машин\w*",
    r"\+\s*-",
    r"\+\s*\d+\s*мин\w*",
    r"(?<![\w-])т(?![\w-])",
    r"\(?\s*платк\w*\s+в\s+(?:сумме|цене)\s*\)?",
    r"ждут\s+с\s+\w+",
    r"желательно\s+\w+",
    r"взять\s+заказ",
    r"запросить",
    r"(?:на|в)\s+(?:руки|рученьки)",
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
    r"(?<!\w)(?:комфорт\s*\+|стандарт|комфорт|минивэн|минивен|компакт-?в[эе]н|эконом|бизнес|вип|vip)(?!\w)",
    r"(?<!\w)(?:примерно|около|ориентировочно)(?!\w)",
    r"№\s*\d+",
    r"(?<!\w)свободен(?!\w)",
    r"(?<!\w)блок\w*",
    r"(?<!\w)легков\w+",
    r"с\s+пустым\s+багажником",
    r"(?<!\w)постоянник\w*",
    r"\+?\s*у\s+каждого\s+багаж\w*",
    r"на\s+бенз\w*",
    r"\d+\s*шт\w*",
    r"·",
    r"готовы\s+ехать",
    r"(?<!\w)(?:девушк\w*|собачк\w*|кошк\w*)(?!\w)",
    r"(?<!\w)врем[яи](?!\w)",
    r"(?<!\w)срочн(?:ый|ая|о)(?!\w)",
    r"пишите,?\s+сколько\s+времени\s+подача",
    r"подъезд\s*\d+",
    r"^\s*багажник.*$",
    r"(?:забрать|забрав\w*)\s+(?:девушк\w*|парня|мужчин\w*|женщин\w*|пассажир\w*)(?:\s+с\s+собачк\w*(?:\s+маленьк\w*)?)?",
    r"(?<!\w)адрес(?!\w)",
    r"выбор\w*\s+то(?!\w)",
    r"(?<!\w)без\s+запрещенк\w*",
    r"(?<!\w)запрещенк\w*",
    r"\d+\s*мин(?=\s*$)",
    r"(?<!\w)до\s*$",
    r"(?<!\w)или\s*$",
    r"(?<!\w)за\s+км(?!\w)",
    r"(?<!\w)плюс(?!\w)",
    r"(?<!\w)по(?=[\s,;]*$)",
    r"^\s*ул(?:\.|\s|$).*$",
    r"\d+(?:[.,]\d+)?\s*кг(?:\s+\d+(?:/\d+)+)?",
    r"(?<!\w)\d+(?:/\d+){2}(?!\w)",
    r"(?<!\w)\+(?=[\s,;]*$)",
]

STOP_RE = re.compile(r"план\s+работы|по\s+заказу\s+пока\s+стоп|возьму\s+заказ|(?<!\w)стоп(?!\w)", re.I)

LABELS = {
    "откуда": "from", "а": "from", "a": "from", "от": "from", "куда": "to", "б": "to", "b": "to", "в": "to", "до": "to",
    "сумма водителю": "price", "стоимость": "price", "стоимость поездки": "price", "цена поездки": "price", "цена": "price",
    "оплата": "price", "сумма": "price",
    "дата/время поездки": "time", "когда": "time", "дата": "time", "время": "time",
    "класс авто": "class", "класс": "class", "тариф": "tariff",
    "дополнительная информация": "comment", "комментарии": "comment",
    "комментарий": "comment", "номер заявки": "id",
}
LABEL_RE = re.compile(r"^([A-Za-zА-Яа-яЁё/ ]{1,30}?)\s*[:.]\s*(.*)$")

FOOTER_RE = re.compile(
    r"можно\s+работать|полная\s+информация|если\s+вы\s+не\s+можете|нажмите|подписк|администратор|"
    r"бот\s+по\s+поиску|контакт\s+диспетчера|по\s+кнопке|@\w+|реклам|перейти\s+к\s+заказу", re.I)
REGION_HEADER_RE = re.compile(
    r"^[\w-]+(?:ский|ская|кая|ной)\s+(?:край|обл\.?|область)$|^(?:республика|респ\.?)\s+[\w-]+$", re.I)
PREP_ONLY = {"до", "в", "из", "от", "на", "во", "с", "со", "→"}
ADDR_CUT_RE = re.compile(
    r"\s+(?:площадк\w*|площадь|садов\w+|снт|днт|тсн|ул\.?|улица|пр-т|проспект|пер\.?|переулок|шоссе|наб\.?|набережная|бульвар|б-р|мкр\.?|микрорайон|корп\.?|кв\.?|дом)(?!\w)"
    r"|\s+д\.?\s*\d", re.I)
ADDRISH_RE = re.compile(
    r"(?<!\w)(?:аэропорт\w*|автовокзал\w*|вокзал\w*|ул\.?|улица|бульвар|проспект|пр-т|переулок|шоссе|набережная|мкр\.?|микрорайон)(?!\w)",
    re.I)
REGION_RE = re.compile(r"обл|респ|край|район|р-н|р-он|округ", re.I)
PLACE_PREFIX_RE = re.compile(
    r"^(?:апп|кпп|пгт|ст|гор|г|город|с|п|пос|посёлок|поселок|ст-ца|станица|х|хутор|д|дер|деревня)\.?[\s,]+",
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


def _ampm_min(m) -> str:
    h = int(m.group(1))
    if m.group(3).lower() in ("вечера", "дня") and h < 12:
        h += 12
    return f" {h}:{m.group(2)} "


def _emoji_labels(t: str) -> str:
    """Формат «📍 откуда … 🏁 куда»: эмодзи -> метки «Откуда:» / «Куда:», продолжение адреса склеивается."""
    if "📍" not in t or "🏁" not in t:
        return t
    out: list[str] = []
    cur = None
    for ln in t.split("\n"):
        st = ln.strip()
        if st.startswith("📍") or st.startswith("🏁"):
            if cur:
                out.append(cur)
            rest = st[1:].strip()
            cur = rest if re.match(r"^(?:откуда|куда|от|до|[аб])\s*[:.]", rest, re.I) else ("Откуда: " if st.startswith("📍") else "Куда: ") + rest
        elif cur and st and not EMOJI_RE.match(st):
            cur += " " + st                      # продолжение адреса на следующей строке
        else:
            if cur:
                out.append(cur)
                cur = None
            out.append(ln)
    if cur:
        out.append(cur)
    return "\n".join(out)


def normalize(text: str) -> list[str]:
    t = text.replace("\u00a0", " ").replace("\u202f", " ")
    t = _emoji_labels(t)
    t = ARROW_RE.sub(" → ", t)
    t = EMOJI_RE.sub(" ", t)
    t = t.replace("«", " ").replace("»", " ")
    t = re.sub(r"(?<![\w])\+\s*(\d{1,3})\s*(мин\w*)",
               lambda m: m.group(0) if re.search(r"\d{1,2}:\d{2}\s*$", m.string[:m.start()]) else f"через {m.group(1)} {m.group(2)}",
               t, flags=re.I)                           # «Сейчас +30 мин»; «в 15:00 +15 мин» остаётся допуском
    t = re.sub(r"(?<![\d:.])(\d{1,2})\s*[-–]\s*\d{1,2}:(\d{2})(?!\d)", r"\1:00", t)         # «14-15:00»
    t = re.sub(r"(?<!\w)через\s+(\d{1,2})[.:](\d{2})(?!\d)", lambda m: f"через {int(m.group(1)) * 60 + int(m.group(2))} мин", t, flags=re.I)   # «через 1.30»
    t = re.sub(r"(?<![\d:.])(0?[6-9]|1\d|2[0-3])\s*[-–]\s*\d{1,2}\s*час\w*", r"\1:00", t, flags=re.I)   # «14-15 часов»
    t = re.sub(r"(?<!\d)(\d{1,2});([0-5]\d)(?!\d)", r"\1:\2", t)
    t = re.sub(r"(?<![\d:.,])(\d{1,2})[ \t]+:[ \t]*([0-5]\d)(?!\d)", r"\1:\2", t)
    t = re.sub(r"(?<=\bдо )([01]?\d|2[0-3])[ \t]*ч(?![\wа-яё])", r"\1:00", t, flags=re.I)   # «до 18ч»
    t = re.sub(r"(?<![\d:.,])((?:[01]?\d|2[0-3]))\.(00|1[3-9]|[2-5]\d)(?![\d.,:])", r"\1:\2", t)   # «16.00», «17.30»
    t = re.sub(r"(?<![\d.,])(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\.?)[ \t]+(\d{1,2})\.([0-5]\d)(?!\d)", r"\1 \2:\3", t)   # «30.10 19.00»
    t = re.sub(r"(?<![\d,.])(\d{1,2}),([0-5]\d)(?!\d)", r"\1:\2", t)
    t = re.sub(r"(?<![\d:.])(\d{1,2}):([0-5]\d)\s*(утра|ночи|вечера|дня)(?!\w)", _ampm_min, t, flags=re.I)   # «5:30 утра»
    t = re.sub(r"(?<![\d:.])(\d{1,2})\s*(утра|ночи|вечера|дня)(?!\w)", _ampm, t, flags=re.I)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    merged: list[str] = []
    for ln in (ln for ln in lines if ln):
        if re.match(r"^пользователь\s+\S+\s+(?:является|находится)", ln, re.I):
            continue                               # строка про чёрный список, не заказ
        ln = re.sub(r"^причина\s*:\s*", "", ln, flags=re.I)
        if merged and ln.lower().strip(" .") in CONT_WORDS:
            merged[-1] += " " + ln
        else:
            merged.append(ln)
    # отдельная строка «ДНР» / «ЛНР» относится к следующей строке
    i = 0
    while i < len(merged) - 1:
        if merged[i].strip(" .,").upper() in ("ДНР", "ЛНР", "ХНР", "ЗНР"):
            merged[i + 1] += " " + merged[i].strip(" .,").upper()
            del merged[i]
        else:
            i += 1
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
    t = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*г(?:ода|\.)?(?!\w)", " ", t)                 # «не старше 2023г»
    t = re.sub(r"\+\s*платк\w*\s*\d+\s*(?:р|₽|руб\w*)?(?!\w)", " + платка", t, flags=re.I)   # «21 тыс +платка 500 р»
    tm = re.search(r"(?<![\d.,])(\d{1,3}(?:[. ]\d{3})+|\d{3,6})\s*\+\s*\d{3,5}\s*платк", t, re.I)
    if tm and 500 <= int(re.sub(r"[. ]", "", tm.group(1))) <= 500000:       # «30000+5000 платка», «47.000 + 3000 платка»
        return int(re.sub(r"[. ]", "", tm.group(1))), ("на руки" if re.search(r"на\s+руки", text, re.I) else None)
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
            sh = re.search(r"(?<![\d.,])(\d{1,2})[ \t]*(?:₽|р(?!\w)|руб|на\s+руки|водител)", t, re.I)   # «8₽» = 8 000
            if not sh or int(sh.group(1)) < 3:
                return None, None
            cands = [(int(sh.group(1)) * 1000, "")]
    money = re.compile(r"^\s*(?:₽|р(?!\w)|руб|т\.?\s?р|на\s+руки|общ|\+\s*плат)", re.I)
    adj = [c for c in cands if money.match(c[1])]
    price = (adj[0] if adj else cands[-1])[0]
    kind = None
    if re.search(r"(?:на|в)\s+(?:руки|рученьки)", text, re.I):
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
    m = re.search(r"(?<=\d{3})\s*[/:]\s*(\d{1,4})(\s*%)?", text)
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
        m = re.match(r"^(?:диспетчер|информация\s+от|в\s+работу)\s*[:\-–—]\s*(.*)$", ln, re.I)
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
    text = re.sub(r"бесплатк\w*", " ", text, flags=re.I)
    if re.search(r"\+\s*\d+\s*платк", text, re.I):
        return "extra"
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
    urgent = bool(re.search(r"(?<!\w)(?:сейчас|срочно)(?!\w)|ближайш(?:ему|ий|ая)(?!\w)|ближ\w*\s+(?:врем\w*|авто|машин\w*)", text, re.I))
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
    if re.search(r"минивэн|минивен|компакт-?в[эе]н", t):
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
    if FOOTER_RE.search(st) or re.match(r"^(?:диспетчер|пользователь\s+@)", st, re.I):
        return ""               # служебные строки ботов-агрегаторов и «Диспетчер: …»
    if st.startswith("(") and st.rstrip(" .").endswith(")"):
        return ""               # строка целиком в скобках: «(место по согласованию)»
    t = _remove(line, EXTRACT_TOKENS)
    t = re.sub(r"(?<=\s)(ЛНР|ДНР|ХНР|ЗНР)\s*[-–—]\s*(?=\S)", r"\1 — ", t, flags=re.I)   # «Шахтерск ДНР-Ростов»
    if not re.search(r"(?<!\w)из\s", t, re.I):          # «КПП Весело Вознесенка отвести в Таганрог»
        t = re.sub(r"\s+(?:отвести|отвезти|вести|довезти|доставить|подвезти|везти)\s+(?=(?:в|во|до|на)\s)", " → ", t, flags=re.I)
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
    s = re.sub(r"\(\s*,\s*", "(", s)             # «( , от Гуково)» после вырезанных «4 км»
    tm = re.search(r"(?:пос[её]лок(?:\s+городского\s+типа)?|пгт|село|деревня|хутор|станица)\s+([А-ЯЁ][\w-]+(?:\s+[А-ЯЁ][\w-]+)?)", s, re.I)
    if tm and "," in s:                     # «Новосветловская участковая больница, посёлок городского типа Новосветловка, …»
        hint0 = ", ".join(reversed([p.strip() for p in s[:tm.start()].strip(" ,").split(",") if p.strip()]))   # район, область
        return tm.group(1), hint0 or None
    pr = s.split()
    if len(pr) >= 2 and is_rostov(pr[0]) and not any(w[:1].isupper() for w in pr[1:]) and "(" not in s and "," not in s:
        return ROSTOV, " ".join(pr[1:])    # «Ростов эксоноил»: после Ростова идёт описание места
    pm0 = re.match(r"^([^(,]+?)\s*\(([^)]*,[^)]*)\)\s*$", s)
    if pm0:                                 # город, а в скобках область и район
        city0 = pm0.group(1).strip()
        segs = [x.strip() for x in pm0.group(2).split(",")]
        segs = [x for x in segs if x and not re.match(r"г\.?\s*о\.?", x, re.I) and city0.lower() not in x.lower()]
        return city0, ", ".join(segs) or None
    vm = re.search(r"\s(?:с|п|пос|ст|д|х|хут)\.\s*([А-ЯЁ][\w-]+)\s*$", " " + s)
    if vm and vm.start() > 0:               # «Ростовская обл., Матвеево-Курганский р-н с. Политотдельское»
        return vm.group(1), (" " + s)[:vm.start()].strip(" ,") or None
    rn = re.match(r"^([А-ЯЁ][\w-]+)\s+район\s+(.+)$", s)
    if rn and not re.search(r"(?:ский|цкий|ий|ый|ой)$", rn.group(1)):
        return rn.group(1), "район " + rn.group(2)    # «Батайск район аэродрома»
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
        hint = ((m.group(1).strip() + (", " + hint if hint else "")) if m.group(1).strip() else hint)
        hint = re.sub(r",\s*,", ",", re.sub(r"^[,\s]+|[,\s]+$", "", hint or "")) or None
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
        while re.search(r"\s[а-яё]+(?:ая|яя|ый|ий|ой|ое)$", city.strip()):
            city = city.strip().rsplit(" ", 1)[0]   # «Таганрога шестая садовая площадка» -> «Таганрога»
    if re.search(r"\s\d+\s*[а-яёa-z]?$", city.strip(), re.I) and " " in city.strip().rsplit(" ", 1)[0].strip():
        city = city.split()[0]              # «Ростова Нурлы Чева 37»: после города идёт адрес с номером дома
    pm = re.match(r"^(.+?)\s+(под\s+[А-ЯЁA-Z]\w+)$", city.strip())
    if pm:                                  # «Веселое под Донецком»
        city = pm.group(1)
        hint = (hint + ", " if hint else "") + pm.group(2)
    city = re.sub(r"^(?:аэропорт|аэро|вокзал|ж/?д\s+вокзал|жд)\s+", "", city, flags=re.I)
    city = STATION_RE.sub("", city).strip(" ,.")
    city = PLACE_PREFIX_RE.sub("", city).strip(" ,.") or city
    if city.isupper():
        city = city.capitalize()
    if is_rostov(city):
        city = ROSTOV
    return city, hint


ROSTOV_RE = re.compile(
    r"^(?:ростов(?:а|е|у|ом)?(?:[\s-]+на[\s-]+\w+|[\s-]+дон)?"
    r"(?:\s+(?:северный|южный|западный|восточный|центр|центральный|сити|жд|ж/д|вокзал|автовокзал|аэропорт))?|роста)$|^(?:рнд|р-н-д)$", re.I)
ROSTOV_PREFIX_RE = re.compile(
    r"^ростов(?:а|е|у|ом)?(?:[\s-]+на[\s-]+дону?|[\s-]+дон)?(?![\w-])(?!\s+великий)(?!\s+на\s)", re.I)
ROSTOV = "Ростов-на-Дону"


def is_rostov(city: str) -> bool:
    """«Ростов», «Ростова», «Ростове на Дону», «Ростов-Дон», «РнД» и т.п. = Ростов-на-Дону."""
    return bool(ROSTOV_RE.match(city.strip()))


def canon_raw(raw: str) -> str:
    """Для показа в карточке: начало строки-названия «Ростова …» -> «Ростов-на-Дону …»."""
    return ROSTOV_PREFIX_RE.sub(ROSTOV, raw.strip(), count=1) if raw else raw


HYPHEN_NAMES = {"санкт петербург", "ростов на дону", "каменск шахтинский", "каменск уральский",
                "ивано франковск", "орехово зуево", "комсомольск на амуре", "гусь хрустальный"}


def norm_hyphen(s: str) -> str:
    return re.sub(r"[-–—\s]+", " ", s.lower().replace("ё", "е")).strip()


COMPOUNDS = [(r"матвеев\w*", r"курган\w*"), (r"минеральн\w*", r"вод\w*"), (r"нижн\w+", r"новгород\w*"), (r"велик\w+", r"новгород\w*"),
             (r"набережн\w+", r"челн\w*"), (r"стар\w+|нов\w+", r"оскол\w*"), (r"красн\w+", r"сулин\w*")]


def split_two_places(base: str) -> Optional[tuple[str, str]]:
    """«Донецк Ростов», «Аргун (Чеченская Республика) Махачкала», «Минеральные Воды Волгоград»."""
    toks: list[str] = []
    base = re.sub(r"(?<=\w)\(", " (", base)
    pending = None
    for m in re.finditer(r"\([^)]*\)|\S+", base):
        t = m.group(0)
        if t.startswith("(") and toks:
            toks[-1] += " " + t
        elif t.lower().rstrip(".") in ("станица", "ст", "село", "с", "поселок", "посёлок", "пгт", "хутор", "х", "деревня", "д", "город", "г"):
            pending = t                     # «станица Ивановская» — одно название
        else:
            toks.append((pending + " " + t) if pending else t)
            pending = None
    out: list[str] = []
    for t in toks:
        if out and t.lower() in ("жд", "ж/д", "аэропорт", "аэро", "вокзал", "автовокзал", "днр", "лнр", "хнр", "знр") and "(" not in out[-1]:
            out[-1] += " " + t              # «Ростов ЖД Таганрог», «Краснодар аэропорт Ростов-на-Дону»
        elif out and any(re.fullmatch(a, out[-1].split()[-1], re.I) and re.fullmatch(b, t, re.I)
                       for a, b in COMPOUNDS) and "(" not in out[-1]:
            out[-1] += " " + t
        else:
            out.append(t)
    def cap(w: str) -> bool:
        return re.sub(r"^(?:станица|ст|село|с|поселок|посёлок|пгт|хутор|х|деревня|д|город|г)\.?\s+", "", w, flags=re.I)[:1].isupper()

    if len(out) == 2 and all(cap(w) for w in out):
        return out[0], out[1]
    plain = [re.sub(r"\([^)]*\)", "", w).strip() for w in out]
    known = {c.lower() for c in CITIES}
    if len(out) == 2 and any(is_rostov(w) or w.split()[0].lower() in known for w in plain) and all(re.fullmatch(r"[А-Яа-яЁё -]{4,}", w) for w in plain):
        return out[0], out[1]               # «Ростов лутугино»: второе название с маленькой буквы
    return None


CONNECTOR_RE = re.compile(r"[-–—➡→>]+")


def route_chain(lines: list[str]) -> list[str]:
    """Маршрут точками на отдельных строках через тире: «Ст. Гривенская (край) - / Ростов - / Любимовка (обл)»."""
    for ln in lines:                        # одна строка «А-Б-В»: откуда А, куда В, через Б
        c = clean_line(ln, strip_preps=False)
        parts = [p.strip() for p in re.split(r"(?<=\S)-(?=\S)", c)]
        if len(parts) >= 3 and all(p and p[:1].isupper() and len(p) > 3 and "(" not in p and ")" not in p
                                   and p.lower() not in ("на", "под") for p in parts) and not any(
                norm_hyphen(f"{parts[i]}-{parts[i + 1]}") in HYPHEN_NAMES for i in range(len(parts) - 1)):
            return parts
    toks: list[list] = []                   # ["P", текст, связь_после] | ["C"]
    for ln in lines:
        st = ln.strip()
        if not st:
            continue
        if CONNECTOR_RE.fullmatch(st):
            toks.append(["C"])
            continue
        tail = bool(re.search(r"\s[-–—]\s*$", st))
        st = st.rstrip(" -–—").strip()
        if st.startswith("(") and st.endswith(")") and toks and toks[-1][0] == "P":
            toks[-1][1] += " " + st                  # «(Краснодарский край)» относится к предыдущей точке
            toks[-1][2] = toks[-1][2] or tail
            continue
        c = clean_line(st, strip_preps=False)
        if c:
            toks.append(["P", c, tail])
    pts = []                                # (текст, связан_со_следующей)
    for i, t in enumerate(toks):
        if t[0] != "P":
            continue
        nxt_c = i + 1 < len(toks) and toks[i + 1][0] == "C"
        pts.append((t[1], t[2] or nxt_c))
    best: list[str] = []
    run: list[str] = []
    for text, linked in pts:
        run.append(text)
        if not linked:
            if len(run) >= 3 and len(run) > len(best):
                best = run
            run = []
    if len(run) >= 3 and len(run) > len(best):
        best = run
    return best


def find_route(lines: list[str]) -> tuple[Optional[str], Optional[str], str]:
    chain = route_chain(lines)
    if chain:
        return chain[0], chain[-1], "medium"
    for ln in lines:                    # «из А в Б»
        c = clean_line(ln, strip_preps=False)
        m = re.match(r"^(?:из|от|с|со)\s+(.+?)\s+(?:в|во|до|на(?!\s+дон))\s+(.+)$", c, re.I)
        if m:
            return m.group(1).strip(" ,"), m.group(2).strip(" ,"), "high"
    for ln in lines:                    # «…отвезти документы из А в Б»: «из» не в начале строки
        c = clean_line(ln, strip_preps=False)
        m = re.search(r"(?<!\w)из\s+(.+?)\s+(?:в|во|до|на(?!\s+дон))\s+(.+)$", c, re.I)
        if m:
            return m.group(1).strip(" ,"), m.group(2).strip(" ,"), "high"
    for ln in lines:                    # «из Таганрога а Ростов» (опечатка вместо «в»)
        c = clean_line(ln, strip_preps=False)
        m = re.search(r"(?<!\w)из\s+(\S+(?:\s\S+)?)\s+а\s+(\S.*)$", c, re.I)
        if m:
            return m.group(1).strip(" ,"), m.group(2).strip(" ,"), "high"
    for ln in lines:                    # «Батайск район аэродрома до Таганрога»
        c = clean_line(ln, strip_preps=False)
        m = re.match(r"^([А-ЯЁ].*?)\s+до\s+([А-ЯЁ].+)$", c)
        if m and not re.search(r"\sдо\s", m.group(2)):
            return m.group(1).strip(" ,"), m.group(2).strip(" ,"), "medium"
    cl = [c for c in (clean_line(ln) for ln in lines) if c]
    for i, c in enumerate(cl):
        if "→" in c:
            segs = [p for p in c.split("→")]
            left = strip_prep(segs[0].strip(" ,.-–—"))
            right = strip_prep(("→".join(segs[1:]) if len(segs) == 2 else segs[-1]).strip(" ,.-–—"))
            if not left and i > 0:
                left = cl[i - 1]
            if not right and i + 1 < len(cl):
                right = cl[i + 1]
            if left and right:
                return left, right, "high"
    for c in cl:
        parts = re.split(r"\s+[-–—]\s+|\s+-(?=[^\s\d])|(?<=[^\s\d])-\s+|\s*[–—]\s*|(?<=жд)-(?=[^\s\d])|(?<=ж/д)-|(?<=вокзал)-|(?<=аэропорт)-|(?<=дону)-(?=[^\s\d])|(?<=вознесенка)-(?=[^\s\d])",
                         c, maxsplit=1, flags=re.I)
        if len(parts) == 2 and all(p.strip() for p in parts):
            return strip_prep(parts[0]), strip_prep(parts[1]), "high"
    if len(cl) == 1:                    # «Донецк Ростов», «Донецк-Ростов»: два названия без разделителя
        base = STATION_RE.sub("", cl[0]).strip()
        two = split_two_places(base)
        if two:
            return two[0], two[1], "low"
        hy = re.fullmatch(r"([А-ЯЁA-Z][\w]+)-([А-ЯЁA-Z][\w]+)", base)
        if hy and norm_hyphen(base) not in HYPHEN_NAMES:
            return hy.group(1), hy.group(2), "low"
        hy = re.search(r"(?<![\w-])([А-ЯЁ][а-яё]+)-([А-ЯЁ][а-яё]+)(?![\w-])", base)   # пара внутри строки
        if hy and norm_hyphen(hy.group(0)) not in HYPHEN_NAMES:
            return hy.group(1), hy.group(2), "low"
    if len(cl) == 4 and ADDRISH_RE.search(cl[1]) and ADDRISH_RE.search(cl[3]) \
            and not ADDRISH_RE.search(cl[0]) and not ADDRISH_RE.search(cl[2]):
        return f"{cl[0]}, {cl[1]}", f"{cl[2]}, {cl[3]}", "medium"   # город и адрес на отдельных строках
    merged_cl: list[str] = []               # «Ростов-на-Дону / Пригородный автовокзал / пос. Весёлый / Ростовская обл»
    for c in cl:
        first = c.split()[0].lower() if c.split() else ""
        attach = bool(merged_cl) and (
            (ADDRISH_RE.search(c) and (re.search(r"(?:ый|ий|ой|ая)$", first) or len(c.split()) == 1))
            or re.fullmatch(r"[А-ЯЁ]\w+\s+(?:обл\w*|край|респ\w*|район)\.?", c))
        if attach:
            merged_cl[-1] += ", " + c
        else:
            merged_cl.append(c)
    if len(merged_cl) < len(cl):
        cl = merged_cl
    addr_lines = [c for c in cl if re.fullmatch(r"[А-ЯЁ][\w-]+(?:\s+[А-ЯЁ][\w-]+)+\s+\d+[а-яa-z]?", c)]
    if len(addr_lines) == 2:                # «Таганрог Инструментальная 35 / Покровское Энгельса 15»
        return addr_lines[0], addr_lines[1], "medium"
    reg_lines = [c for c in cl if re.search(r"(?:област\w+|обл\.?|край|республик\w+)$", c, re.I)]
    if len(reg_lines) == 2 and reg_lines[0] != reg_lines[1]:
        return reg_lines[0], reg_lines[1], "medium"   # «Курган Курганская область / Курорт … Курганская область»
    known_low = {c.lower() for c in CITIES}
    for c in cl:                            # «таганрог-Кафе петросис»: известный город, дефис, место
        if "-" in c and c.split("-", 1)[0].lower() in known_low and c.split("-", 1)[1].strip():
            return c.split("-", 1)[0], c.split("-", 1)[1].strip(), "low"
    hy_lines = [c for c in cl if re.fullmatch(r"[А-ЯЁ][а-яё]+-[А-ЯЁ][а-яё]+", c) and norm_hyphen(c) not in HYPHEN_NAMES]
    if len(hy_lines) == 1 and (len(cl) >= 3 or any(len(c.split()) >= 3 for c in cl if c != hy_lines[0])):
        a, b = hy_lines[0].split("-")       # «Батайск-Элиста» среди строк про багаж и постоянников
        return a, b, "low"
    if len(cl) >= 3:
        two = [c for c in cl if re.fullmatch(r"[А-ЯЁ][а-яё-]+ [А-ЯЁ][а-яё-]+", c) and split_two_places(c)]
        if len(two) == 1:                   # «Луганск Ростов» среди строк про багаж
            a, b = split_two_places(two[0])
            return a, b, "low"
    if len(cl) >= 2:
        return cl[0], cl[1], ("medium" if len(cl) == 2 else "low")
    return None, None, "low"


def find_via(lines: list[str]) -> list[str]:
    """Промежуточные точки маршрута «A → B → C» (например, пункт пропуска)."""
    chain = route_chain(lines)
    if chain:
        return [parse_place(x)[0] for x in chain[1:-1]]
    for ln in lines:
        c = clean_line(ln, strip_preps=False)
        segs = [strip_prep(p.strip(" ,.-–—")) for p in c.split("→")]
        if len(segs) >= 3 and all(segs):
            return [parse_place(x)[0] if "," not in x else x.split(",")[-1].strip() for x in segs[1:-1]]
    return []


MULTI_LINE_RE = re.compile(r"^\s*\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?(?:\s+\d{1,2}[.:]\d{2}\b|,\s*[А-ЯЁ])")


def split_multi(text: str) -> list[str]:
    """Сообщение со списком заказов (каждый начинается со строки «30.10 22.00 …») -> отдельные тексты."""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if MULTI_LINE_RE.match(ln)]
    if len(starts) < 2:
        return [text]
    blocks = []
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[i:end]).strip())
    return blocks


NUM_WORDS = {"один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5}


def _num(token: str) -> int:
    first = token.split()[0].lower().rstrip(".")
    nums = re.findall(r"\d+", first)
    if nums:
        return max(int(x) for x in nums)         # «1-3чел» -> 3
    return NUM_WORDS.get(re.sub(r"[^а-я]", "", first), 1)


def parse_order(text: str, allow_unrouted: bool = False) -> Optional[Order]:
    if not text or len(text) > 1500 or STOP_RE.search(text):
        return None
    lines = normalize(text)

    labeled: dict[str, str] = {}
    body: list[str] = []
    for ln in lines:
        m = LABEL_RE.match(ln)
        key = LABELS.get(m.group(1).strip().lower()) if m else None
        if not key:                            # «Откуда Таганрог», «Куда Белая Калитва» без двоеточия
            m = re.match(r"^(откуда|куда)\s+(\S.*)$", ln, re.I)
            key = LABELS.get(m.group(1).lower()) if m else None
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

    from_raw, to_raw = canon_raw(from_raw), canon_raw(to_raw)
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
    km = re.search(r"(\d+)\s*км", re.sub(r"\([^)]*\)", " ", full), re.I)     # «(4 км от Гуково)» — не расстояние поездки
    pct, fee_rub = extract_commission(full)
    if pct is None and fee_rub is None:
        pm2 = re.search(r"(\d{1,2})\s*%", full)
        pct = int(pm2.group(1)) if pm2 else None

    if price is None and not time_text and not urgent:
        return None
    if conf == "none" and price is None:
        return None                         # нет ни маршрута, ни цены: вопрос в чате, не заказ

    comment = labeled.get("comment")
    if not comment:
        extras = []
        for pat in (r"\d+\s*адрес\w*",
                    r"(?:\d+[ \t]*)?(?:детей|дети|ребёнок|ребенок)(?:[ \t]*:[ \t]*\d+)?(?:[ \t]*\(?[ \t]*\d+(?:[ \t]*(?:и|,)[ \t]*\d+)*[ \t]*(?:лет|года|год)[ \t]*\)?)?",
                    r"(?:нужен\s+)?бустер\w*",
                    r"(?<![\d.])(?:\+7|8)\d{10}(?!\d)",
                    r"(?:маленьк\w+\s+)?(?:собак\w*|собачк\w*|кошк\w*)(?:\s+на\s+руках)?",
                    r"\d+\s*дам\w*\s*\+\s*бейб\w*",
                    r"детск\w+\s+кресл\w+(?:\s+обязательн\w+)?"):
            am = re.search(pat, full, re.I)
            if am:
                extras.append(am.group(0).strip())
        extras = [("тел. " + e) if re.fullmatch(r"(?:\+7|8)\d{10}", e) else e for e in extras]
        comment = "; ".join(extras) if extras else None
    if comment:
        comment = re.sub(r"\s*\(\s*", " (", comment)
        comment = re.sub(r"\s*\)", ")", comment)
    if comment and len(re.findall(r"[A-Za-zА-Яа-яЁё]", re.sub(PASS, "", comment, flags=re.I))) < 3:
        comment = None

    tm = re.search(r"\d{3,6}\s*\+\s*(\d{3,5})\s*платк", full, re.I)
    if tm:
        comment = (comment + "; " if comment else "") + f"платка {int(tm.group(1)):,} ₽".replace(",", " ")
    kg = re.findall(r"\d+(?:[.,]\d+)?\s*кг(?:[ \t]+\d+(?:/\d+)+)?", full, re.I)
    if kg:
        comment = (comment + "; " if comment else "") + "груз: " + "; ".join(k.strip() for k in kg)
    mm = re.search(r"(?<!\w)(?:\d+|две|два|три)\s+машин\w*", full, re.I)
    if mm:
        comment = (comment + "; " if comment else "") + mm.group(0).lower()
    via = find_via(body) if conf != "none" else []
    if via:
        comment = (comment + "; " if comment else "") + "через " + ", ".join(via)
    disp, disp_user = extract_dispatcher(lines)
    addr = bool(from_raw and (ADDR_CUT_RE.search(from_raw.split(",")[0]) or ADDR_CUT_RE.search(to_raw.split(",")[0])
                              or re.search(r"\s\d+\s*[а-яё]?$", from_raw.split(",")[0].strip(), re.I)))
    from_city, from_hint = parse_place(from_raw)
    to_city, to_hint = parse_place(to_raw)
    # в карточке и для расчёта города в именительном падеже: «из Таганрога» -> «Таганрог»
    from_city, to_city = nominative(from_city), nominative(to_city)
    from_raw, to_raw = nominative(from_raw), nominative(to_raw)
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
