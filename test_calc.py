import asyncio

from calc import calculate, place_queries, trip_price
from cards import format_calc
from order_parser import parse_order
from test_parser import SAMPLES

S = {n: parse_order(t) for n, t, _ in SAMPLES}
RATES = {"Стандарт": 27, "Комфорт": 30, "Комфорт+": 35, "Минивэн": 50}
bad = 0


def check(name, got, want):
    global bad
    ok = got == want
    bad += not ok
    print("OK  " if ok else "FAIL", name, "" if ok else f"ждали {want!r}, получили {got!r}")


class FakeGeo:
    def __init__(self, coords, km):
        self.coords, self.km = coords, km

    async def place_coords(self, city, hint):
        return self.coords.get(city)

    async def route_km(self, a, b):
        return self.km.get((a, b))


# формулы как в SWTCalcBot
check("650 км × 27", trip_price(650, 27, False, 20), (17550, 17600))
check("650 км × 27, срочная", trip_price(650, 27, True, 20), (21060, 21100))
check("округление .5 вверх", trip_price(100, 27.5, False, 20)[0], 2750)

# запросы к карте
check("область", place_queries("Куйбышево", "запорожская обл"), ["Куйбышево, Запорожская область", "Куйбышево"])
check("Ростов северный -> Ростов-на-Дону", place_queries("Ростов северный", None), ["Ростов-на-Дону"])
check("ЛНР", place_queries("Марковка", "ЛНР"), ["Марковка, Луганская область", "Марковка"])
check("район", place_queries("Металлист", "Амвросиевский р-он"), ["Металлист, Амвросиевский район", "Металлист"])
check("обычный город", place_queries("Каменка", None), ["Каменка"])

geo = FakeGeo({"Ростов-на-Дону": (1.0, 1.0), "Астрахань": (2.0, 2.0)},
              {((1.0, 1.0), (2.0, 2.0)): 700.0})
r = asyncio.run(calculate(S["city2city"], RATES, 20, geo))
check("Ростов→Астрахань: расчёт", (r.ok, r.calc_price, r.diff, r.km_source), (True, 18900, 2100, "карта"))

r = asyncio.run(calculate(S["СтоДорог"], RATES, 20, FakeGeo({}, {})))
check("Калуга→Москва: км из заказа, Комфорт", (r.ok, r.calc_price, r.diff, r.km_source), (True, 5700, 1300, "км из заказа"))

r = asyncio.run(calculate(S["Марковка"], RATES, 20, FakeGeo({}, {})))
check("нет городов на карте и нет км", (r.ok, r.reason), (False, "не нашёл города на карте"))

geo2 = FakeGeo({"Ростов-на-Дону": (1.0, 1.0), "Богураев": (1.0, 1.01)}, {((1.0, 1.0), (1.0, 1.01)): 100.0})
r = asyncio.run(calculate(S["ProPoisk-карточка"], RATES, 20, geo2))
check("срочный заказ: 100 км Стандарт +20%", (r.calc_price, r.urgent, r.diff), (3200, True, 800))

o = parse_order("Ростов → Москва бизнес 9000 сегодня 17:00")
r = asyncio.run(calculate(o, RATES, 20, FakeGeo({}, {})))
check("неизвестный класс", r.ok, False)

un = parse_order("Кто едет из Ростова в Москву? Сегодня 17:00 5000", allow_unrouted=True)
r = asyncio.run(calculate(un, RATES, 20, FakeGeo({}, {})))
check("маршрут не распознан", (r.ok, r.reason), (False, "маршрут не распознан"))

print()
for name in ("city2city", "СтоДорог"):
    o = S[name]
    print(format_calc(asyncio.run(calculate(o, RATES, 20, FakeGeo({"Ростов-на-Дону": (1.0, 1.0), "Астрахань": (2.0, 2.0)}, {((1.0, 1.0), (2.0, 2.0)): 700.0}))), o))
    print("---")
print("Провалено:", bad)
raise SystemExit(bad)
