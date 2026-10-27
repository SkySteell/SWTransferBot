"""Настройки фильтров: хранятся в JSON-файле, переживают перезапуск."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

# Обычные тарифы ₽/км, как в SWTCalcBot
DEFAULT_RATES = {"Стандарт": 27, "Комфорт": 30, "Комфорт+": 35, "Минивэн": 50}

DATA_DIR = os.environ.get("DATA_DIR", "data")
PATH = os.path.join(DATA_DIR, "settings.json")


@dataclass
class Settings:
    enabled: bool = True
    min_price: int = 0
    from_cities: list = field(default_factory=list)
    to_cities: list = field(default_factory=list)
    time_mode: str = "any"      # any | urgent | within
    time_hours: int = 3
    unknown_ok: bool = False    # показывать заказы, где цену/время нельзя проверить
    rates: dict = field(default_factory=lambda: dict(DEFAULT_RATES))
    urgent_pct: int = 20        # надбавка за срочность, %
    muted_chats: list = field(default_factory=list)   # id групп, которые не мониторим


def load() -> Settings:
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        known = Settings.__dataclass_fields__
        st = Settings(**{k: v for k, v in data.items() if k in known})
        st.rates = {**DEFAULT_RATES, **st.rates}
        return st
    except (FileNotFoundError, ValueError, TypeError):
        return Settings()


def save(s: Settings) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(s), f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)
