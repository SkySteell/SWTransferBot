"""Названия мест в именительном падеже: «Таганрога» -> «Таганрог», «в Москву» -> «Москва».

Без словаря городов: правила по окончаниям плюс списки исключений. Для незнакомых названий
правило может ошибиться, тогда название остаётся как в заказе.
"""
from __future__ import annotations

import re

# Выглядят как косвенный падеж, но уже стоят в именительном
KNOWN_NOM = {
    "сочи", "мытищи", "ессентуки", "химки", "шахты", "воды", "минеральные", "жуковский", "баку", "тбилиси",
    "ессентуков", "кемерово", "иваново", "подольск", "анапа", "москва", "тула", "самара", "уфа", "чита", "пенза",
    "вологда", "кострома", "алушта", "ялта", "волноваха", "махачкала", "ижевск", "сызрань", "дубна", "керчь",
    "ростов", "таганрог", "азов", "аксай", "батайск", "донецк", "луганск", "краснодар", "новгород", "тверь",
}
IRREGULAR = {
    "орла": "Орёл", "орле": "Орёл", "орлу": "Орёл", "ельца": "Елец", "ельце": "Елец",
    "шахт": "Шахты", "шахтах": "Шахты", "шахтам": "Шахты",
    "львова": "Львов", "пскова": "Псков", "севастополя": "Севастополь",
}
# окончания родительного падежа мужского рода: Таганрога, Донецка, Краснодара, Азова ...
GEN_A = ("нта", "ога", "ска", "цка", "ова", "ева", "ёва", "ара", "ада", "ода", "ежа", "она", "ака", "ика", "аза",
         "рга", "ира", "ава", "ёна")
SKIP = {"жд", "ж/д", "аэропорт", "аэро", "вокзал", "автовокзал", "апп", "кпп", "центр", "северный", "южный",
        "западный", "восточный", "сити", "район", "область", "на", "в", "под", "и", "или"}


def _word(w: str) -> str:
    lw = w.lower()
    if lw in KNOWN_NOM:
        return w
    if lw in IRREGULAR:
        return IRREGULAR[lw]
    if len(lw) < 4:
        return w
    # прилагательные: Нижнего -> Нижний, Красного -> Красный, Каменск-Шахтинского -> ...-Шахтинский
    if lw.endswith("ского"):
        return w[:-5] + "ский"
    if lw.endswith("цкого"):
        return w[:-5] + "цкий"
    if lw.endswith("ого"):
        return w[:-3] + "ый"
    if lw.endswith("его"):
        return w[:-3] + "ий"
    if lw.endswith("ии") and len(lw) > 5:                 # Феодосии, Евпатории
        return w[:-1] + "я"
    if lw.endswith(("поля", "поле")) and len(lw) > 7:    # Мелитополя, Симферополя, в Мариуполе
        return w[:-1] + "ь"
    if lw.endswith("у"):                                  # в Москву, на Успенку, в Волноваху
        return w[:-1] + "а"
    if lw.endswith("ы"):                                  # из Москвы, Ялты, Анапы
        return w[:-1] + "а"
    if lw.endswith("и"):
        stem = w[:-1]
        last = stem[-1].lower()
        if last in "кгх":                                 # Горловки, Волновахи
            return stem + "а"
        if stem.lower().endswith(("ан", "ен", "ер", "рм", "рч")):   # Казани, Рязани, Тюмени, Перми, Керчи
            return stem + "ь"
        return w                                          # Балтаси, Сочи и т.п. остаются как есть
    if lw.endswith(GEN_A):
        return w[:-1]
    if lw.endswith("е") and len(lw) > 4 and lw[-2] not in "оеиыуаяюёэ":   # в Таганроге, в Москве
        stem = w[:-1]
        if stem.lower() in {"москв", "тул", "анап", "пенз", "самар", "уф", "чит"}:
            return stem + "а"
        return stem
    return w


def _token(tok: str) -> str:
    """Слово с возможным дефисом: Санкт-Петербурга, Каменск-Шахтинского."""
    if tok.isupper() and len(tok) > 3:
        tok = tok.capitalize()
    parts = tok.split("-")
    if "на" in parts[1:-1]:                               # Ростов-на-Дону, Славянск-на-Кубани: форма фиксированная
        return tok
    return "-".join(_word(p) if p[:1].isupper() or len(parts) == 1 else p for p in parts)


PHRASES = {"мин воды": "Минеральные Воды", "минводы": "Минеральные Воды", "минеральный воды": "Минеральные Воды",
           "мин. воды": "Минеральные Воды", "минеральных вод": "Минеральные Воды"}


def nominative(phrase: str) -> str:
    """Название места (город с возможным адресом) в именительном падеже, первая буква заглавная."""
    if not phrase or not phrase.strip():
        return phrase
    s = phrase.strip()
    for k, v in PHRASES.items():            # устойчивые сокращения и опечатки
        if s.lower() == k or s.lower().startswith(k + " ") and not re.search(r"[(,]", s.lower()[:len(k)]):
            return v + s[len(k):]
    m = re.search(r"[(,]", s)
    head, tail = (s[:m.start()], s[m.start():]) if m else (s, "")
    words = head.split()
    adj_first = len(words) == 2 and words[0].lower().endswith(("ого", "его"))   # «красного десанта» -> «Красный Десант»
    out = []
    for i, w in enumerate(words):
        if w.lower() in SKIP or re.search(r"[\d.]", w) or not w[:1].isalpha():
            out.append(w)
        elif i == 0 or (len(words) <= 2 and (w[:1].isupper() or adj_first)):
            out.append(_token(w[:1].upper() + w[1:]))
        else:
            out.append(w)
    head = " ".join(out)
    # «Ростовская область, Волгодонска»: после региона тоже город
    if tail.startswith(",") and re.search(r"(?:област|респ|край|район|округ)\w*$", head, re.I):
        rest = tail[1:].strip()
        w0, _, more = rest.partition(" ")
        tail = ", " + (_token(w0[:1].upper() + w0[1:]) + (" " + more if more else "") if w0 else "")
    return head + (" " if head and tail and tail[0] == "(" and head[-1] != " " else "") + tail
