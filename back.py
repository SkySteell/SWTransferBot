"""Обратка: заказы с отправлением рядом с городом, куда вы едете, в ближайшие сутки."""
from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Iterable, Optional

from calc import haversine
from filters import norm, pickup_datetime
from order_parser import Order
from settings import Settings


@dataclass
class Meta:
    """Откуда пришёл заказ: нужно, чтобы показать карточку позже (источник, диспетчер, приём)."""
    chat_id: int
    msg_id: int
    group: str
    dispatcher: str
    username: Optional[str]
    link: Optional[str]
    text: str
    dm_only: bool
    now: datetime


@dataclass
class Rec:
    key: str
    order: Order
    meta: Meta


def passes_back(o: Order, s: Settings, now: datetime, order_now: datetime, hours: int = 24) -> tuple[bool, str]:
    """Фильтры для обратки: пауза, мин. сумма, подача в ближайшие сутки (без времени тоже). Списки городов не применяются; отключённые группы вообще не читаются ботом."""
    if not s.enabled:
        return False, "пауза"
    if s.min_price > 0:
        if o.price is None:
            if not s.unknown_ok:
                return False, "нет цены"
        elif o.price < s.min_price:
            return False, "цена ниже минимума"
    pt = pickup_datetime(o, order_now)
    if pt is None:
        return True, ""                     # заказы без времени показываем всегда: город и радиус проверяются отдельно
    if not (now - timedelta(minutes=30) <= pt <= now + timedelta(hours=hours)):
        return False, "время вне окна"
    return True, ""


def min_distance(a_list: list, b_list: list) -> float:
    return min(haversine(a, b) for a in a_list for b in b_list)


async def search_back(recs: Iterable[Rec], target: list, label: str, radius: float, cfg: Settings, now: datetime,
                      coords_of: Callable[[Order], Awaitable[list]], hours: int = 24, deadline: float = 45.0
                      ) -> tuple[list[tuple[float, Rec]], int]:
    """(найденные [(км, заказ)] по близости, сколько городов не успели проверить)."""
    found: list[tuple[float, Rec]] = []
    unchecked = 0
    t0 = _time.monotonic()
    want = norm(label)
    for rec in sorted(recs, key=lambda r: r.meta.now, reverse=True):
        o = rec.order
        ok, _ = passes_back(o, cfg, now, rec.meta.now, hours)
        if not ok:
            continue
        if norm(o.from_city) == want:
            found.append((0.0, rec))
            continue
        if _time.monotonic() - t0 > deadline:
            unchecked += 1
            continue
        coords = await coords_of(o)
        if not coords:
            continue
        d = min_distance(coords, target)
        if d <= radius:
            found.append((d, rec))
    found.sort(key=lambda x: (round(x[0] / 10), pickup_datetime(x[1].order, x[1].meta.now) or now))
    return found, unchecked
