import asyncio
from datetime import datetime, timedelta, timezone

from back import Meta, Rec, passes_back, search_back
from order_parser import parse_order
from settings import Settings

TZ = timezone(timedelta(hours=3))
NOW = datetime(2026, 11, 5, 14, 30, tzinfo=TZ)
bad = 0


def check(name, got, want):
    global bad
    ok = got == want
    bad += not ok
    print("OK  " if ok else "FAIL", name, "" if ok else f"ждали {want!r}, получили {got!r}")


def rec(text, mins_ago=0, key=None):
    o = parse_order(text)
    return Rec(key or text, o, Meta(1, 1, "Группа", "-", None, None, text, False, NOW - timedelta(minutes=mins_ago)))


S = Settings()
check("в окне 24 ч", passes_back(rec("Сегодня 18:00 Таганрог - Ростов 2000").order, S, NOW, NOW)[0], True)
check("завтра в пределах суток", passes_back(rec("Завтра 09:00 Таганрог - Ростов 2000").order, S, NOW, NOW)[0], True)
check("через 2 суток вне окна", passes_back(rec("07.11 12:00 Таганрог - Ростов 2000").order, S, NOW, NOW)[0], False)
check("прошло давно", passes_back(rec("Сегодня 09:00 Таганрог - Ростов 2000").order, S, NOW, NOW)[0], False)
check("время неизвестно показываем всегда", passes_back(rec("Таганрог - Ростов 2000 на руки").order, S, NOW, NOW)[0], True)
check("время неизвестно, если разрешено", passes_back(rec("Таганрог - Ростов 2000 на руки").order, Settings(unknown_ok=True), NOW, NOW)[0], True)
check("мин. сумма", passes_back(rec("Сегодня 18:00 Таганрог - Ростов 2000").order, Settings(min_price=3000), NOW, NOW)[1], "цена ниже минимума")
check("пауза", passes_back(rec("Сегодня 18:00 Таганрог - Ростов 2000").order, Settings(enabled=False), NOW, NOW)[1], "пауза")
check("города фильтра не применяются", passes_back(rec("Сегодня 18:00 Таганрог - Ростов 2000").order, Settings(from_cities=["Москва"]), NOW, NOW)[0], True)
check("срочный, поданный давно: уже не актуален", passes_back(rec("Сейчас Таганрог - Ростов 2000", 300).order, S, NOW, NOW - timedelta(minutes=300))[0], False)

# поиск: Ростов (1,1) — цель; Таганрог рядом (80 км), Москва далеко
COORDS = {"Азов": [(1.0, 1.4)], "Таганрог": [(1.0, 1.9)], "Москва": [(9.0, 9.0)]}


async def coords_of(o):
    return COORDS.get(o.from_city, [])


recs = [rec("Сегодня 18:00 Азов - Москва 5000"), rec("Сегодня 19:00 Москва - Ростов 9000"),
        rec("Сегодня 20:00 Ростов - Казань 9000"), rec("Сегодня 17:00 Таганрог - Москва 8000"),
        rec("Послезавтра 12:00 Азов - Москва 5000")]
from calc import haversine
d_az = haversine((1.0, 1.0), (1.0, 1.4)); d_tg = haversine((1.0, 1.0), (1.0, 1.9))
res, unchecked = asyncio.run(search_back(recs, [(1.0, 1.0)], "Ростов-на-Дону", 100.0, S, NOW, coords_of))
names = [(r.order.from_city, round(d)) for d, r in res]
check("найдены Ростов (0 км) и Азов, Таганрог дальше радиуса", names, [("Ростов-на-Дону", 0), ("Азов", round(d_az))])
res, _ = asyncio.run(search_back(recs, [(1.0, 1.0)], "Ростов-на-Дону", 200.0, S, NOW, coords_of))
check("радиус 200: добавился Таганрог", [r.order.from_city for d, r in res], ["Ростов-на-Дону", "Азов", "Таганрог"])
res, _ = asyncio.run(search_back(recs, [(1.0, 1.0)], "Ростов-на-Дону", 100.0, S, NOW, coords_of, deadline=-1))
check("при исчерпанном времени без карты находятся только совпадения по названию", [r.order.from_city for d, r in res], ["Ростов-на-Дону"])
res, un = asyncio.run(search_back(recs, [(1.0, 1.0)], "Ростов-на-Дону", 100.0, S, NOW, coords_of, deadline=-1))
check("непроверенных городов", un, 3)
print("\nПровалено:", bad)
raise SystemExit(bad)
