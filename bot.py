"""Этап 2: юзербот читает ваши группы, парсит заказы, фильтрует и присылает карточки в бот.

Переменные окружения: API_ID, API_HASH, SESSION_STRING, BOT_TOKEN, OWNER_ID.
Необязательные: DATA_DIR (папка для settings.json, по умолчанию data),
TZ_OFFSET (часовой пояс, по умолчанию 3 = Москва).
Пустой список городов (откуда или куда) означает «любые».
Расчёт по калькулятору и автоприём добавляются на следующих этапах.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

from telethon import Button, TelegramClient, events
from telethon.errors import MessageNotModifiedError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, User

import groups as groups_store
import settings as settings_store
from calc import Geo, calculate
from cards import format_card
from filters import merge_cities, passes
from order_parser import Order, parse_order

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orderbot")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET", "3"))))

DEDUPE_TTL = 6 * 3600
RAW_KEEP = 500

user = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot = TelegramClient(StringSession(), API_ID, API_HASH)

cfg = settings_store.load()
geo = Geo(os.path.join(settings_store.DATA_DIR, "geocache.json"))
bg_tasks: set = set()
groups = groups_store.load()          # все группы и каналы аккаунта {id: {title, kind}}
group_stats: Counter = Counter()  # сколько заказов распознано по группам с запуска
seen: dict[str, float] = {}
raw_texts: "OrderedDict[int, str]" = OrderedDict()
stats: Counter = Counter()
pending: Optional[str] = None   # какую настройку владелец сейчас вводит


# ---------- дубли и вспомогательное ----------

def dedupe_key(o: Order) -> str:
    if o.route_confidence == "none":
        base = " ".join(o.raw_text.lower().split())
    else:
        base = "|".join(str(x).lower() for x in (o.from_city, o.to_city, o.price, o.time_text))
    return hashlib.sha1(base.encode()).hexdigest()


def is_duplicate(o: Order) -> bool:
    now = time.time()
    for k in [k for k, t in seen.items() if now - t > DEDUPE_TTL]:
        del seen[k]
    key = dedupe_key(o)
    if key in seen:
        return True
    seen[key] = now
    return False


def source_link(chat, msg_id: int) -> Optional[str]:
    if not isinstance(chat, Channel):
        return None
    if chat.username:
        return f"https://t.me/{chat.username}/{msg_id}"
    return f"https://t.me/c/{chat.id}/{msg_id}"


def who(sender, msg) -> tuple[str, Optional[str]]:
    if msg.fwd_from and getattr(msg.fwd_from, "from_name", None):
        return msg.fwd_from.from_name, None
    if sender is None:
        return "—", None
    username = getattr(sender, "username", None)
    if isinstance(sender, User):
        name = " ".join(filter(None, [sender.first_name, sender.last_name])) or username or str(sender.id)
    else:
        name = getattr(sender, "title", None) or "—"
    return name, username


async def refresh_groups() -> int:
    """Читает все диалоги аккаунта и собирает список групп и каналов."""
    found: dict[int, dict] = {}
    async for d in user.iter_dialogs():
        if d.is_user:
            continue
        if d.is_group or d.is_channel:
            found[d.id] = {"title": d.name or str(d.id), "kind": "группа" if d.is_group else "канал"}
    if found:
        groups.clear()
        groups.update(found)
        groups_store.save(groups)
    return len(groups)


async def attach_calc(sent, order: Order, dispatcher: str, group: str, rows) -> None:
    """Считает стоимость по калькулятору и дописывает её в уже отправленную карточку."""
    try:
        res = await asyncio.wait_for(calculate(order, cfg.rates, cfg.urgent_pct, geo), timeout=60)
        stats["расчёт выполнен" if res.ok else "расчёт невозможен"] += 1
        text = format_card(order, dispatcher, group, res)
    except Exception:
        log.exception("Ошибка расчёта")
        text = format_card(order, dispatcher, group, calc_error="ошибка карты")
    try:
        await sent.edit(text, buttons=rows, link_preview=False)
    except Exception:
        pass  # карточку могли скрыть или изменить


# ---------- чтение групп ----------

@user.on(events.NewMessage(incoming=True))
async def on_message(event: events.NewMessage.Event) -> None:
    if event.is_private or not event.raw_text:
        return
    cid = event.chat_id
    if cid not in groups:   # вступили в новую группу после запуска
        try:
            chat = await event.get_chat()
            groups[cid] = {"title": getattr(chat, "title", None) or str(cid),
                           "kind": "канал" if getattr(chat, "broadcast", False) else "группа"}
            groups_store.save(groups)
        except Exception:
            pass
    if cid in cfg.muted_chats:
        return
    try:
        order = parse_order(event.raw_text, allow_unrouted=bool(cfg.from_cities or cfg.to_cities))
        if order is None:
            return
        stats["заказов распознано"] += 1
        group_stats[cid] += 1
        ok, reason = passes(order, cfg, datetime.now(TZ))
        if not ok:
            stats[f"отсеяно: {reason}"] += 1
            return
        if is_duplicate(order):
            stats["дублей"] += 1
            return

        chat = await event.get_chat()
        sender = await event.get_sender()
        _, sender_username = who(sender, event.message)
        # настоящий диспетчер берётся из текста заказа, а не отправитель-бот (решение 30.10)
        dispatcher = order.dispatcher or "-"
        username = order.dispatcher_username or (None if getattr(sender, "bot", False) else sender_username)
        group = getattr(chat, "title", None) or "—"

        rows = []
        first = []
        link = source_link(chat, event.message.id)
        if link:
            first.append(Button.url("🔗 Источник", link))
        if username:
            first.append(Button.url("💬 Диспетчер", f"https://t.me/{username}"))
        if first:
            rows.append(first)
        rows.append([Button.inline("🙈 Скрыть", b"hide"), Button.inline("⚠️ Ошибка", b"bad")])

        sent = await bot.send_message(
            OWNER_ID, format_card(order, dispatcher, group, None),
            buttons=rows, link_preview=False,
        )
        stats["отправлено"] += 1
        raw_texts[sent.id] = event.raw_text
        while len(raw_texts) > RAW_KEEP:
            raw_texts.popitem(last=False)
        task = asyncio.create_task(attach_calc(sent, order, dispatcher, group, rows))
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
    except Exception:
        log.exception("Ошибка обработки сообщения")


# ---------- меню настроек ----------

def settings_text() -> str:
    c = cfg
    time_line = {
        "any": "любое",
        "urgent": "только срочные",
        "within": f"в ближайшие {c.time_hours} ч",
    }[c.time_mode]
    return "\n".join([
        "⚙️ Настройки фильтров",
        f"Статус: {'▶️ работает' if c.enabled else '⏸ пауза'}",
        f"💰 Мин. сумма: {f'{c.min_price:,}'.replace(',', ' ') + ' ₽' if c.min_price else 'не задана'}",
        f"📍 Откуда: {', '.join(c.from_cities) if c.from_cities else 'любые'}",
        f"🏁 Куда: {', '.join(c.to_cities) if c.to_cities else 'любые'}",
        *(["   ↔️ ищу: из «Откуда» куда угодно, откуда угодно в «Куда», и между ними"]
          if c.from_cities and c.to_cities else []),
        f"⏱ Время подачи: {time_line}",
        f"❓ Без цены/времени: {'показывать' if c.unknown_ok else 'скрывать'}",
        f"📋 Группы: мониторится {groups_store.active_count(groups, cfg.muted_chats)} из {len(groups)}"
        if groups else "📋 Группы: список появится после запуска",
        "🧮 Тарифы ₽/км: " + " / ".join(str(c.rates[t]) for t in TARIFFS) + f" · срочность +{c.urgent_pct}%",
    ])


def settings_buttons():
    return [
        [Button.inline("💰 Сумма", b"set:min_price"), Button.inline("📍 Откуда", b"set:from"),
         Button.inline("🏁 Куда", b"set:to")],
        [Button.inline("⏱ Время", b"set:time"), Button.inline("❓ Неизвестное", b"set:unknown")],
        [Button.inline("📋 Группы", b"set:groups"), Button.inline("🧮 Тарифы", b"set:rates")],
        [Button.inline("⏸ Пауза" if cfg.enabled else "▶️ Включить", b"set:enabled")],
    ]


TARIFFS = ["Стандарт", "Комфорт", "Комфорт+", "Минивэн"]


def rates_text() -> str:
    lines = ["🧮 Тарифы калькулятора (₽/км)"]
    lines += [f"{t}: {cfg.rates[t]}" for t in TARIFFS]
    lines.append(f"Срочность: +{cfg.urgent_pct}%")
    lines.append("\nНажмите на тариф, чтобы изменить цену за километр.")
    return "\n".join(lines)


def rates_buttons():
    rows = [[Button.inline(f"{t}: {cfg.rates[t]}", f"rate:{t}".encode())] for t in TARIFFS]
    rows.append([Button.inline(f"Срочность: +{cfg.urgent_pct}%", b"rate:urgent")])
    rows.append([Button.inline("← Назад", b"set:back")])
    return rows


def groups_text() -> str:
    return "\n".join([
        "📋 Группы и каналы аккаунта",
        f"Мониторится: {groups_store.active_count(groups, cfg.muted_chats)} из {len(groups)}",
        "✅ слушаем, ⬜ отключено. Нажмите на название, чтобы переключить.",
        "Число в скобках: сколько заказов распознано из группы с запуска.",
    ])


def groups_buttons(page: int):
    items, page = groups_store.page_items(groups, page)
    pages = groups_store.page_count(len(groups))
    rows = []
    for cid, g in items:
        mark = "⬜" if cid in cfg.muted_chats else "✅"
        n = group_stats.get(cid)
        label = f"{mark} {groups_store.short(g.get('title'))}" + (f" ({n})" if n else "")
        rows.append([Button.inline(label, f"gt:{page}:{cid}".encode())])
    nav = []
    if page > 0:
        nav.append(Button.inline("◀️", f"gp:{page - 1}".encode()))
    nav.append(Button.inline(f"{page + 1}/{pages}", b"noop"))
    if page < pages - 1:
        nav.append(Button.inline("▶️", f"gp:{page + 1}".encode()))
    rows.append(nav)
    rows.append([Button.inline("✅ Все", f"ga:1:{page}".encode()),
                 Button.inline("⬜ Ни одной", f"ga:0:{page}".encode()),
                 Button.inline("🔄 Обновить", f"gr:{page}".encode())])
    rows.append([Button.inline("← Назад", b"set:back")])
    return rows


async def show_groups(event, page: int) -> None:
    try:
        await event.edit(groups_text(), buttons=groups_buttons(page))
    except MessageNotModifiedError:
        pass


async def handle_groups_cb(event, data: bytes) -> bool:
    parts = data.decode().split(":")
    kind = parts[0]
    if kind == "noop":
        await event.answer()
    elif kind == "gp":
        await event.answer()
        await show_groups(event, int(parts[1]))
    elif kind == "gt":
        await event.answer()
        cfg.muted_chats = groups_store.toggle(cfg.muted_chats, int(parts[2]))
        settings_store.save(cfg)
        await show_groups(event, int(parts[1]))
    elif kind == "ga":
        await event.answer()
        cfg.muted_chats = [] if parts[1] == "1" else list(groups.keys())
        settings_store.save(cfg)
        await show_groups(event, int(parts[2]))
    elif kind == "gr":
        await event.answer("Обновляю список…")
        try:
            await refresh_groups()
        except Exception:
            log.exception("Не удалось обновить список групп")
        await show_groups(event, int(parts[1]))
    else:
        return False
    return True


def prompt_text(action: str) -> str:
    if action not in {"from", "to"}:
        return PROMPTS[action]
    current = cfg.from_cities if action == "from" else cfg.to_cities
    return (PROMPTS[action]
            + f"\n\nСейчас: {', '.join(current) if current else 'пусто (любые)'}"
            + "\nУдалить город: напишите его с минусом, например -Батайск."
            + "\nОчистить весь список: отправьте «-».")


BTN_SETTINGS = "⚙️ Настройки"
BTN_STATS = "📊 Статистика"
MAIN_KB = [[Button.text(BTN_SETTINGS, resize=True), Button.text(BTN_STATS, resize=True)]]


def stats_text() -> str:
    lines = ["📊 С момента запуска:"] + ([f"{k}: {v}" for k, v in stats.most_common()] or ["пока пусто"])
    return "\n".join(lines)


def parse_list(text: str) -> list[str]:
    if text.strip() in {"-", "0", "нет", "сброс"}:
        return []
    parts = [p.strip() for p in text.replace(";", ",").replace("\n", ",").split(",")]
    return [p for p in parts if p]


PROMPTS = {
    "min_price": "Отправьте минимальную сумму числом (например 5000). «-» сбросит.",
    "from": "Отправьте города отправления через запятую (например: Ростов, Батайск). Они добавятся к списку.",
    "to": "Отправьте города назначения через запятую. Они добавятся к списку.",
    "time_hours": "Отправьте число часов (1–72): показывать заказы с подачей в ближайшие N часов.",
    "rate": "Отправьте новую цену за километр (₽), например 28.",
    "urgent": "Отправьте надбавку за срочность в процентах, например 20.",
}


@bot.on(events.NewMessage(incoming=True, from_users=OWNER_ID))
async def on_owner_message(event: events.NewMessage.Event) -> None:
    global pending
    text = event.raw_text.strip()
    if text.startswith("/start"):
        pending = None
        await event.respond("Меню внизу экрана 👇", buttons=MAIN_KB)
        await event.respond(settings_text(), buttons=settings_buttons())
        return
    if text == BTN_SETTINGS or text.startswith("/settings"):
        pending = None
        await event.respond(settings_text(), buttons=settings_buttons())
        return
    if text == BTN_STATS or text.startswith("/stats"):
        await event.respond(stats_text())
        return
    if not pending:
        return
    key, pending = pending, None
    try:
        if key == "min_price":
            digits = "".join(ch for ch in text if ch.isdigit())
            cfg.min_price = int(digits) if digits and text != "-" else 0
        elif key == "from":
            cfg.from_cities = merge_cities(cfg.from_cities, text)
        elif key == "to":
            cfg.to_cities = merge_cities(cfg.to_cities, text)
        elif key == "time_hours":
            cfg.time_hours = max(1, min(72, int(text)))
            cfg.time_mode = "within"
        elif key.startswith("rate:"):
            val = float(text.replace(",", "."))
            if not 0 < val <= 1000:
                raise ValueError
            val = int(val) if val.is_integer() else val
            target = key.split(":", 1)[1]
            if target == "urgent":
                cfg.urgent_pct = int(val)
            else:
                cfg.rates[target] = val
    except ValueError:
        pending = key
        await event.respond("Не понял, отправьте число.")
        return
    settings_store.save(cfg)
    if key.startswith("rate:"):
        await event.respond("✅ Сохранено\n\n" + rates_text(), buttons=rates_buttons())
    else:
        await event.respond("✅ Сохранено\n\n" + settings_text(), buttons=settings_buttons())


@bot.on(events.CallbackQuery)
async def on_callback(event: events.CallbackQuery.Event) -> None:
    global pending
    if event.sender_id != OWNER_ID:
        return
    data = event.data
    if data == b"hide":
        await event.delete()
        return
    if data == b"bad":
        raw = raw_texts.get(event.message_id)
        await event.answer("Исходный текст отправлен ниже" if raw else "Текст уже не сохранён")
        if raw:
            await bot.send_message(OWNER_ID, "Перешлите это сообщение разработчику:\n\n" + raw)
        return
    if data.split(b":")[0] in {b"noop", b"gp", b"gt", b"ga", b"gr"}:
        await handle_groups_cb(event, data)
        return
    if data.startswith(b"rate:"):
        target = data.decode().split(":", 1)[1]
        pending = f"rate:{target}"
        await event.answer()
        await bot.send_message(OWNER_ID, PROMPTS["urgent" if target == "urgent" else "rate"])
        return
    if not data.startswith(b"set:"):
        return

    action = data.decode().split(":", 1)[1]
    if action in {"min_price", "from", "to"}:
        pending = action
        await event.answer()
        await bot.send_message(OWNER_ID, prompt_text(action))
        return
    if action == "groups":
        await event.answer()
        if not groups:
            try:
                await refresh_groups()
            except Exception:
                log.exception("Не удалось получить список групп")
        await show_groups(event, 0)
        return
    if action == "rates":
        await event.answer()
        await event.edit(rates_text(), buttons=rates_buttons())
        return
    if action == "back":
        await event.answer()
        try:
            await event.edit(settings_text(), buttons=settings_buttons())
        except MessageNotModifiedError:
            pass
        return
    if action == "time":
        order = ["any", "urgent", "within"]
        cfg.time_mode = order[(order.index(cfg.time_mode) + 1) % 3]
        if cfg.time_mode == "within":
            pending = "time_hours"
            await bot.send_message(OWNER_ID, PROMPTS["time_hours"])
    elif action == "unknown":
        cfg.unknown_ok = not cfg.unknown_ok
    elif action == "enabled":
        cfg.enabled = not cfg.enabled
    settings_store.save(cfg)
    await event.answer()
    await event.edit(settings_text(), buttons=settings_buttons())


async def main() -> None:
    await user.connect()
    if not await user.is_user_authorized():
        raise SystemExit("SESSION_STRING недействителен: создайте новый через make_session.py")
    await bot.start(bot_token=BOT_TOKEN)
    try:
        total = await refresh_groups()
    except Exception:
        log.exception("Не удалось получить список групп")
        total = len(groups)
    try:
        await bot.send_message(
            OWNER_ID,
            f"✅ Бот запущен. Найдено групп и каналов: {total}.\n"
            "Отключить лишние: «⚙️ Настройки», затем «📋 Группы».",
            buttons=MAIN_KB)
    except Exception:
        log.warning("Не удалось написать владельцу: откройте бота и нажмите /start")
    log.info("Запущено")
    await asyncio.gather(user.run_until_disconnected(), bot.run_until_disconnected())


if __name__ == "__main__":
    asyncio.run(main())
