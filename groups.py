"""Список групп и каналов аккаунта: хранение, страницы, отключение ненужных."""
from __future__ import annotations

import json
import os
from math import ceil

from settings import DATA_DIR

PATH = os.path.join(DATA_DIR, "groups.json")
PER_PAGE = 8


def load() -> dict[int, dict]:
    try:
        with open(PATH, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, ValueError):
        return {}


def save(groups: dict[int, dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in groups.items()}, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def sorted_items(groups: dict[int, dict]) -> list[tuple[int, dict]]:
    return sorted(groups.items(), key=lambda kv: (kv[1].get("title") or "").lower())


def page_count(n: int) -> int:
    return max(1, ceil(n / PER_PAGE))


def page_items(groups: dict[int, dict], page: int) -> tuple[list[tuple[int, dict]], int]:
    items = sorted_items(groups)
    page = max(0, min(page, page_count(len(items)) - 1))
    return items[page * PER_PAGE:(page + 1) * PER_PAGE], page


def toggle(muted: list[int], cid: int) -> list[int]:
    return [c for c in muted if c != cid] if cid in muted else muted + [cid]


def active_count(groups: dict[int, dict], muted: list[int]) -> int:
    return sum(1 for c in groups if c not in muted)


def short(title: str, n: int = 28) -> str:
    title = " ".join((title or "без названия").split())
    return title if len(title) <= n else title[: n - 1] + "…"
