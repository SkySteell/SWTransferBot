import asyncio

from calc import best_pair, calculate, candidate_ok, hint_norm, place_queries, trip_price, word_ok
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
check("ЛНР", place_queries("Марковка", "ЛНР"), ["Марковка, Луганская область", "Марковка", "Марковк"])
check("район", place_queries("Металлист", "Амвросиевский р-он"), ["Металлист, Амвросиевский район", "Металлист"])
check("«место по согласованию» не регион", place_queries("Ростов на Дону", "место по согласованию"), ["Ростов-на-Дону"])
check("обычный город + запасная форма", place_queries("Каменка", None), ["Каменка", "Каменк"])
check("красного десанта -> красный десант", place_queries("красного десанта", None), ["красного десанта", "красного-десанта", "красный десант", "красный-десант"])
check("Ростов на коммунистический", place_queries("Ростов на коммунистический", None), ["Ростов-на-Дону"])
check("Ростова -> Ростов-на-Дону", place_queries("Ростова", None), ["Ростов-на-Дону"])
check("Москву", place_queries("Москву", None), ["Москву", "Москва"])
check("Казани", place_queries("Казани", None), ["Казани", "Казань"])

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

kz = parse_order("Когда: 27.10.2026 01:00\nОткуда: Ростов на Дону (место по согласованию)\nКуда: Казань\nЦена: 40000₽")
r = asyncio.run(calculate(kz, RATES, 20, FakeGeo({"Ростов на Дону": (1.0, 1.0), "Казань": (2.0, 2.0)}, {((1.0, 1.0), (2.0, 2.0)): 1486.0})))
check("Ростов→Казань 1486 км", (r.calc_price, r.diff), (40100, -100))
print(format_calc(r, kz))
# проверка результата карты: склонения и посторонние совпадения
check("Батайска ~ Батайск", word_ok("батайска", "батайск"), True)
check("Батайска не Бат", word_ok("батайска", "бат"), False)
check("Каменк не Каменка", word_ok("каменк", "каменка"), False)
check("Нижний Новгород принят", candidate_ok("Нижний Новгород", ["Нижний Новгород", "Приволжский округ"]), True)
check("чужое название отклонено", candidate_ok("Батайска", ["Улица Батайская", "Ростов"]), False)
check("регион в названии", candidate_ok("Ростов-на-Дону", ["городской округ", "Ростов-на-Дону"]), True)

# хинты и новые запросы
check("hint: р-н и обл", hint_norm("Аксайский р-н, Ростовская обл"), "Аксайский район, Ростовская область")
check("hint: ЛНР внутри", hint_norm("антрацитовский район, ЛНР"), "Антрацитовский район, Луганская область")
check("hint: респ", hint_norm("Донецкая Народная респ"), "Донецкая Народная республика")
check("жаргон Марик", place_queries("Марик", None), ["Мариуполь"])
check("Дебальцево Заводской -> Дебальцево", place_queries("Дебальцево Заводской", None),
      ["Дебальцево Заводской", "Дебальцево-Заводской", "Дебальцево"])
check("Весело Вознесеновка", place_queries("Весело Вознесеновка", None),
      ["Весело Вознесеновка", "Весело-Вознесеновка", "Весело Вознесеновк", "Весело-Вознесеновк", "Весело"])
check("двусловное: чужой «Красный …» отклонён", candidate_ok("красный десант", ["Красный Сулин"]), False)
check("двусловное: свой принят", candidate_ok("красный десант", ["Красный Десант"]), True)
check("дефис в результате", candidate_ok("Весело-Вознесеновка", ["Весело-Вознесеновка"]), True)

# одноимённые места: берётся ближайшая пара (Никольское рядом с Ростовом, а не за 9000 км)
near, far = (47.2, 39.7), (69.0, 33.0)
rost = [(47.23, 39.72)]
check("ближайшая пара", best_pair(rost, [far, (47.5, 39.9)]), ((47.23, 39.72), (47.5, 39.9)))

class FakeGeoMulti:
    def __init__(self, coords, km): self.coords, self.km = coords, km
    async def place_coords(self, city, hint): return self.coords.get(city, [])
    async def route_km(self, a, b): return self.km.get((a, b))

nk = parse_order("✅ 28.10 10:00 Ростов-на-Дону - Никольское 5 чел Минивэн 10800 Платка: клиент")
g = FakeGeoMulti({"Ростов-на-Дону": rost, "Никольское": [far, (47.5, 39.9)]},
                 {((47.23, 39.72), (47.5, 39.9)): 60.0, ((47.23, 39.72), far): 9162.0})
r = asyncio.run(calculate(nk, RATES, 20, g))
check("Никольское: 60 км, Минивэн", (r.ok, r.km, r.calc_price), (True, 60.0, 3000))

print()
for name in ("city2city", "СтоДорог"):
    o = S[name]
    print(format_calc(asyncio.run(calculate(o, RATES, 20, FakeGeo({"Ростов-на-Дону": (1.0, 1.0), "Астрахань": (2.0, 2.0)}, {((1.0, 1.0), (2.0, 2.0)): 700.0}))), o))
    print("---")
print("Провалено:", bad)
raise SystemExit(bad)
