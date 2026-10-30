"""Расчёт стоимости поездки по правилам SWTCalcBot (обычный тариф, одна пара точек).

Расстояния: Nominatim (геокодинг) и OSRM (маршрут), как в калькуляторе.
Итог округляется до сотни, срочность +20% к сумме поездки, платные дороги не учитываются.
Названия на карте проверяются, а при нескольких одноимённых местах берётся ближайшая пара.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from filters import norm
from order_parser import Order
from settings import DEFAULT_RATES  # noqa: F401  (реэкспорт для удобства)

HEADERS = {"User-Agent": "transfer-order-bot/1.0 (personal use)"}

# Короткие, жаргонные и неоднозначные названия -> то, что понимает карта.
ALIASES = {
    "ростов": "Ростов-на-Дону", "питер": "Санкт-Петербург", "спб": "Санкт-Петербург",
    "мск": "Москва", "екб": "Екатеринбург", "нижний": "Нижний Новгород",
    "марик": "Мариуполь", "авилоуспенка": "Авило-Успенка",
}
FULL_ALIASES = {"ростов на дону": "Ростов-на-Дону", "санкт петербург": "Санкт-Петербург",
                "мин воды": "Минеральные Воды", "минводы": "Минеральные Воды"}
DISTRICT_WORDS = {"северный", "южный", "западный", "восточный", "центр", "центральный",
                  "сити", "аэропорт", "вокзал", "жд", "ж/д"}
HINT_MAP = {"лнр": "Луганская область", "днр": "Донецкая область",
            "хнр": "Херсонская область", "знр": "Запорожская область"}
REGION_WORDS = ("обл", "респ", "край", "район", "р н", "р он", "округ", "лнр", "днр", "хнр", "знр")


def _r(x: float) -> int:
    return int(math.floor(x + 0.5))


def round100(x: float) -> int:
    return int(math.floor(x / 100 + 0.5) * 100)


def trip_price(km: float, rate: float, urgent: bool, urgent_pct: float) -> tuple[int, int]:
    """(сумма до округления, итог до сотни)."""
    k = 1 + urgent_pct / 100 if urgent else 1
    exact = _r(km * rate * k)
    return exact, round100(exact)


def hint_norm(h: str) -> str:
    key = norm(h)
    if key in HINT_MAP:
        return HINT_MAP[key]
    h = h.strip()
    for k, v in HINT_MAP.items():           # «антрацитовский район, ЛНР» -> «…, Луганская область»
        h = re.sub(rf"(?<!\w){k}(?!\w)", v, h, flags=re.I)
    h = re.sub(r"(?<!\w)обл\.?(?!\w)", "область", h, flags=re.I)
    h = re.sub(r"(?<!\w)р-?(?:он|н)(?!\w)", "район", h, flags=re.I)
    h = re.sub(r"(?<!\w)респ\.?(?!\w)", "республика", h, flags=re.I)
    return h[:1].upper() + h[1:]


def _is_region_hint(hint: str) -> bool:
    """Подсказка помогает карте, только если это регион («место по согласованию» не годится)."""
    h = norm(hint)
    return any(w in h for w in REGION_WORDS)


def _alias_for(word: str) -> Optional[str]:
    for key, val in ALIASES.items():
        if word == key or (len(key) >= 5 and word.startswith(key) and len(word) - len(key) <= 2):
            return val
    return None


def _adjectival(w: str) -> bool:
    return w.lower().endswith(("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ого", "его"))


def declension_variants(city: str) -> list[str]:
    """Запасные формы названия: Москву -> Москва, Ростова -> Ростов, Казани -> Казань."""
    w = city.strip()
    low = w.lower()
    if w.count(" ") == 1 and "-" not in w:      # «красного десанта» -> «красный десант»
        a, b = w.split()
        a2 = (a[:-3] + "ый" if a.lower().endswith("ого") else
              a[:-3] + "ий" if a.lower().endswith("его") else
              a[:-2] + "ая" if a.lower().endswith("ой") else a)
        b2 = (b[:-1] + "а" if b.lower().endswith(("ы", "у")) else
              b[:-1] if b.lower().endswith("а") else b)
        out = [f"{a}-{b}"]                      # «Весело Вознесеновка» -> «Весело-Вознесеновка»
        if f"{a2} {b2}" != w:
            out += [f"{a2} {b2}", f"{a2}-{b2}"]
        return out
    if " " in w or "-" in w or len(w) < 5:
        return []
    out = []
    if low.endswith(("у", "ы", "е")):
        out.append(w[:-1] + "а")
    if low.endswith("а"):
        out.append(w[:-1])
    if low.endswith("и"):
        out.append(w[:-1] + "ь")
    return out


def place_queries(city: str, hint: Optional[str]) -> list[str]:
    if norm(city) in FULL_ALIASES:
        return [FULL_ALIASES[norm(city)]]
    words = norm(city).split()
    if words:
        alias = _alias_for(words[0])
        if alias and (len(words) == 1 or (len(words) == 2 and words[1] in DISTRICT_WORDS)
                      or (len(words) >= 3 and words[1] == "на" and words[2] != "дону")):
            return [alias]
    qs: list[str] = []
    if hint and _is_region_hint(hint):
        qs.append(f"{city}, {hint_norm(hint)}")
    qs.append(city)
    qs += declension_variants(city)
    raw = city.split()
    if len(raw) >= 2 and "-" not in city and not _adjectival(raw[0]):
        for n in range(len(raw) - 1, 0, -1):    # «Дебальцево Заводской» -> «Дебальцево»
            qs.append(" ".join(raw[:n]))
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


# ---------- проверка результата карты ----------

def word_ok(q: str, n: str) -> bool:
    """Первое слово запроса и результата совпадают (с учётом падежа: Батайска ~ Батайск)."""
    if not q or not n:
        return False
    return n == q or (len(n) >= 4 and q.startswith(n) and len(q) - len(n) <= 2)


def candidate_ok(query: str, names: list[str]) -> bool:
    """Результат карты подходит, если совпадает первое слово, а у двусловных названий и второе."""
    q = norm(query.split(",")[0]).split() or [""]
    for nm in names:
        n = norm(nm).split() or [""]
        if not word_ok(q[0], n[0]):
            continue
        if len(q) < 2 or len(n) < 2 or q[1] in {"на", "в", "под", "над"} or word_ok(q[1], n[1]):
            return True
    return False


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def best_pair(A: list, B: list) -> tuple[tuple[float, float], tuple[float, float]]:
    """Из нескольких одноимённых мест выбирает пару ближайших друг к другу."""
    return min(((a, b) for a in A for b in B), key=lambda p: haversine(p[0], p[1]))


def _as_list(c: Any) -> list:
    if not c:
        return []
    if isinstance(c, tuple) and len(c) == 2 and all(isinstance(x, (int, float)) for x in c):
        return [c]
    return list(c)


@dataclass
class CalcResult:
    ok: bool
    tariff: str = "Стандарт"
    km: Optional[float] = None
    km_source: str = ""            # "карта" | "км из заказа"
    calc_price: Optional[int] = None
    diff: Optional[int] = None     # цена заказа минус расчёт
    urgent: bool = False
    urgent_pct: int = 0
    reason: str = ""


class Geo:
    """Геокодинг и маршруты с кэшем на диске и лимитом Nominatim 1 запрос/сек."""

    def __init__(self, cache_path: str):
        self.path = cache_path
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._bad: dict[str, float] = {}
        self._session: Any = None
        self.cache: dict = {"geo": {}, "route": {}}
        try:
            with open(cache_path, encoding="utf-8") as f:
                self.cache.update(json.load(f))
        except (FileNotFoundError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _sess(self) -> Any:
        import aiohttp  # импорт здесь, чтобы тесты без сети работали без aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def geocode(self, query: str) -> list[tuple[float, float]]:
        """Все подходящие по названию места (до 5). Пустой список, если не нашлось."""
        key = "v2:" + norm(query)
        cached = self.cache["geo"].get(key)
        if cached is not None:
            return [(c[0], c[1]) for c in cached]
        if time.time() - self._bad.get(key, 0) < 3600:
            return []
        async with self._lock:
            wait = 1.1 - (time.time() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with self._sess().get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "jsonv2", "limit": 5, "accept-language": "ru"},
                ) as r:
                    data = await r.json(content_type=None)
            except Exception:
                return []
            finally:
                self._last = time.time()
        found: list[tuple[float, float]] = []
        for item in data or []:
            names = [item.get("name", "")] + (item.get("display_name") or "").split(",")[:2]
            if not candidate_ok(query, names):
                continue
            c = (float(item["lat"]), float(item["lon"]))
            if all(haversine(c, f) > 5 for f in found):
                found.append(c)
        if not found:
            self._bad[key] = time.time()
            return []
        self.cache["geo"][key] = [list(c) for c in found]
        self._save()
        return found

    async def place_coords(self, city: str, hint: Optional[str]) -> list[tuple[float, float]]:
        for q in place_queries(city, hint):
            found = await self.geocode(q)
            if found:
                return found
        return []

    async def route_km(self, a: tuple[float, float], b: tuple[float, float]) -> Optional[float]:
        key = f"{a[0]:.3f},{a[1]:.3f}|{b[0]:.3f},{b[1]:.3f}"
        if key in self.cache["route"]:
            return self.cache["route"][key]
        url = f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
        try:
            async with self._sess().get(url, params={"overview": "false"}) as r:
                if r.status != 200:
                    return None
                data = await r.json()
        except Exception:
            return None
        if data.get("code") != "Ok":
            return None
        km = data["routes"][0]["distance"] / 1000
        self.cache["route"][key] = km
        self._save()
        return km


async def calculate(o: Order, rates: dict, urgent_pct: int, geo) -> CalcResult:
    tariff = o.car_class or "Стандарт"
    rate = rates.get(tariff)
    if rate is None:
        return CalcResult(False, tariff=tariff, reason=f"нет тарифа для класса «{tariff}»")

    km, source = None, ""
    if o.route_confidence != "none" and o.from_city and o.to_city:
        A = _as_list(await geo.place_coords(o.from_city, o.from_hint))
        B = _as_list(await geo.place_coords(o.to_city, o.to_hint)) if A else []
        if A and B:
            a, b = best_pair(A, B)
            km = await geo.route_km(a, b)
            source = "карта"
    if km is None and o.distance_km:
        km, source = float(o.distance_km), "км из заказа"
    if km is None:
        reason = "маршрут не распознан" if o.route_confidence == "none" else "не нашёл города на карте"
        return CalcResult(False, tariff=tariff, reason=reason)
    if km < 1:
        return CalcResult(False, tariff=tariff, reason="расстояние слишком мало, проверьте города")

    _, total = trip_price(km, rate, o.urgent, urgent_pct)
    diff = o.price - total if o.price else None
    return CalcResult(True, tariff=tariff, km=km, km_source=source, calc_price=total,
                      diff=diff, urgent=o.urgent, urgent_pct=urgent_pct if o.urgent else 0)
