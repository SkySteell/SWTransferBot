from datetime import datetime, timedelta, timezone

from filters import passes, pickup_datetime
from order_parser import parse_order
from settings import Settings
from test_parser import SAMPLES

NOW = datetime(2026, 10, 24, 11, 46, tzinfo=timezone(timedelta(hours=3)))
S = {n: parse_order(t) for n, t, _ in SAMPLES}


def check(name, order, settings, expected):
    ok, why = passes(order, settings, NOW)
    status = "OK  " if ok == expected else "FAIL"
    print(status, name, "->", ok, why)
    return ok != expected


bad = 0
bad += check("мин. сумма 10000, 21000", S["city2city"], Settings(min_price=10000), True)
bad += check("мин. сумма 10000, 7000", S["СтоДорог"], Settings(min_price=10000), False)
bad += check("откуда Ростов: Ростов северный", S["Руслан"], Settings(from_cities=["Ростов"]), True)
bad += check("откуда Ростов: Ростов-на-Дону", S["city2city"], Settings(from_cities=["Ростов"]), True)
bad += check("откуда Ростов: Калуга", S["СтоДорог"], Settings(from_cities=["Ростов"]), False)
bad += check("куда Москва", S["СтоДорог"], Settings(to_cities=["Москва", "Казань"]), True)
bad += check("куда Москва: Астрахань", S["city2city"], Settings(to_cities=["Москва"]), False)
bad += check("только срочные: Марковка", S["Марковка"], Settings(time_mode="urgent"), True)
bad += check("только срочные: city2city", S["city2city"], Settings(time_mode="urgent"), False)
w = Settings(time_mode="within", time_hours=3)
bad += check("в 3 ч: 13:00", S["Руслан"], w, True)
bad += check("в 3 ч: 23:00", S["Никита-Бугуруслан"], w, False)
bad += check("в 3 ч: +1-1,5 часа", S["Металлист-Киров"], w, True)
bad += check("в 3 ч: 24.10 12:00", S["СтоДорог"], w, True)
bad += check("в 3 ч: 23 октября (прошло)", S["city2city"], w, False)
bad += check("нет цены при мин. сумме", parse_order("Ростов - Москва сегодня 17:00"), Settings(min_price=5000), False)
bad += check("нет цены, unknown_ok", parse_order("Ростов - Москва сегодня 17:00"), Settings(min_price=5000, unknown_ok=True), True)
bad += check("пауза", S["city2city"], Settings(enabled=False), False)
bad += check("все фильтры сразу", S["Марковка"], Settings(min_price=3000, time_mode="urgent", to_cities=["Россошь"]), True)

# --- города независимо: направление там, где маршрут понятен, иначе поиск по тексту
free = "Кто едет из Ростова в Москву? Сегодня 17:00 5000"
bad += 0 if parse_order(free) is None else 1
print("OK  " if parse_order(free) is None else "FAIL", "без разрешения не-маршрут не заказ")
U = parse_order(free, allow_unrouted=True)
bad += check("текстовый поиск: откуда Ростов, куда Москва", U, Settings(from_cities=["Ростов"], to_cities=["Москва"]), True)
bad += check("текстовый поиск: куда Казань", U, Settings(to_cities=["Казань"]), False)
rev = parse_order("Москва → Ростов 5000 сегодня 17:00")
bad += check("направление учитывается: Москва→Ростов, откуда Ростов", rev, Settings(from_cities=["Ростов"]), False)
bad += check("направление учитывается: Москва→Ростов, куда Ростов", rev, Settings(to_cities=["Ростов"]), True)
low = parse_order("Ростов\nВолгоград\nМосква\n5000 сегодня 17:00")
bad += check("маршрут неуверенный: Москва находится в тексте", low, Settings(from_cities=["Москва"]), True)
bad += check("города не заданы: проходит любой", U, Settings(), True)
print("\nПровалено:", bad)
raise SystemExit(bad)
