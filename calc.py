"""Расчёт стоимости поездки по правилам SWTCalcBot (обычный тариф, одна пара точек).

Расстояния: Nominatim (геокодинг) и OSRM (маршрут), как в калькуляторе.
Итог округляется до сотни, срочность +20% к сумме поездки, платные дороги не учитываются.
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

# Короткие и неоднозначные названия -> то, что понимает карта.
ALIASES = {
    "ростов": "Ростов-на-Дону", "питер": "Санкт-Петербург", "спб": "Санкт-Петербург",
    "мск": "Москва", "екб": "Екатеринбург", "нижний": "Нижний Новгород",
}
DISTRICT_WORDS = {"северный", "южный", "западный", "восточный", "центр", "центральный",
                  "сити", "аэропорт", "вокзал", "жд", "ж/д"}
HINT_MAP = {"лнр": "Луганская область", "днр": "Донецкая область",
            "хнр": "Херсонская область", "знр": "Запорожская область"}


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
    h = re.sub(r"(?<!\w)обл\.?$", "область", h.strip(), flags=re.I)
    h = re.sub(r"(?<!\w)р-?(?:он|н)$", "район", h, flags=re.I)
    return h[:1].upper() + h[1:]


def _alias_for(word: str) -> Optional[str]:
    for key, val in ALIASES.items():
        if word == key or (len(key) >= 5 and word.startswith(key) and len(word) - len(key) <= 2):
            return val
    return None


def declension_variants(city: str) -> list[str]:
    """Запасные формы названия: Москву -> Москва, Ростова -> Ростов, Казани -> Казань."""
    w = city.strip()
    low = w.lower()
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
    words = norm(city).split()
    if words:
        alias = _alias_for(words[0])
        if alias and (len(words) == 1 or (len(words) == 2 and words[1] in DISTRICT_WORDS)):
            return [alias]
    qs = []
    if hint:
        qs.append(f"{city}, {hint_norm(hint)}")
    qs.append(city)
    return qs + declension_variants(city)


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

    async def geocode(self, query: str) -> Optional[tuple[float, float]]:
        key = norm(query)
        if key in self.cache["geo"]:
            lat, lon = self.cache["geo"][key]
            return lat, lon
        if time.time() - self._bad.get(key, 0) < 3600:
            return None
        async with self._lock:
            wait = 1.1 - (time.time() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with self._sess().get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "json", "limit": 1, "accept-language": "ru"},
                ) as r:
                    data = await r.json(content_type=None)
            except Exception:
                return None
            finally:
                self._last = time.time()
        if not data:
            self._bad[key] = time.time()
            return None
        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
        self.cache["geo"][key] = [lat, lon]
        self._save()
        return lat, lon

    async def place_coords(self, city: str, hint: Optional[str]) -> Optional[tuple[float, float]]:
        for q in place_queries(city, hint):
            c = await self.geocode(q)
            if c:
                return c
        return None

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
        a = await geo.place_coords(o.from_city, o.from_hint)
        b = await geo.place_coords(o.to_city, o.to_hint) if a else None
        if a and b:
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
