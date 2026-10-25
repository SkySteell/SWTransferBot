from order_parser import parse_order

SAMPLES = [
    # (название, текст, ожидаемое: from_city, to_city, price, поля для проверки)
    ("city2city", """Трансферы city2city.ru
Номер заявки: 2422613896
Откуда: Ростов-на-Дону
Куда: Астрахань
Сумма водителю: 21000
Дата/время поездки: 23 октября 19:00
Дополнительная информация: 1 пассажир""",
     dict(from_city="Ростов-на-Дону", to_city="Астрахань", price=21000,
          price_kind="водителю", passengers=1, time_text="23 октября 19:00", comment=None)),

    ("Руслан", """13:00
Ростов северный
Куйбышево запорожская обл
1 чел 15000🔐🔐🔐""",
     dict(from_city="Ростов северный", to_city="Куйбышево", to_hint="запорожская обл",
          price=15000, passengers=1, time_text="13:00")),

    ("Никита-Бугуруслан", """В 23:00
Северное
Бугуруслан(Оренбургская область)
1 человек
45000 общее
🔒🔒🔒""",
     dict(from_city="Северное", to_city="Бугуруслан", to_hint="Оренбургская область",
          price=45000, price_kind="общее", passengers=1, time_text="23:00")),

    ("Металлист-Киров", "+1 -1,5 часа , Металлист (Амвросиевский р-он) - Киров , 1чел . 45.000+платка 🔐",
     dict(from_city="Металлист", from_hint="Амвросиевский р-он", to_city="Киров", price=45000, tolls="extra", passengers=1)),

    ("Марковка", """СЕЙЧАС ‼️

МАРКОВКА (ЛНР)

РОССОШЬ

ПИШЕМ ВРЕМЯ ПОДАЧИ

5000""",
     dict(from_city="Марковка", from_hint="ЛНР", to_city="Россошь", price=5000, urgent=True)),

    ("Воронеж", """Воронеж

Когда: сегодня 17:00

Класс авто: ВЫБОР АВТО

А: Воронеж адрес

Б: пгт, Каменка

Стоимость: 5000р на руки

Комментарии: авто без рекламы, постоянница""",
     dict(from_city="Воронеж", to_city="Каменка", price=5000, price_kind="на руки",
          time_text="сегодня 17:00", car_class=None)),

    ("Казань", """Ждут с Казани.

📍Пгт. Балтаси
—>
📍Казань

Тариф: Камри и тп
📍5.500/10% с предоплатой""",
     dict(from_city="Балтаси", to_city="Казань", price=5500, percent=10)),

    ("СтоДорог", """✅✅✅ЗАКАЗ✅✅✅
🗓 24.10. 🕰 12:00
🚕 Комфорт, желательно кроссовер
⚡️ Нет
🚌 Калуга, микрорайон Анненки ➡️ Москва, Беговая улица
📏 190 км
👛 7000 на руки
✉️ 2 пасс., 4 сумки, пару корзинок  Нужен вместительный багажник.
СтоДорог
#Заказ185048""",
     dict(from_city="Калуга", to_city="Москва", price=7000, price_kind="на руки",
          passengers=2, car_class="Комфорт", distance_km=190, time_text="24.10 12:00")),

    ("ProPoisk-карточка", """ЗАКАЗ · ⚡ СРОЧНО · сегодня
📍 Ростов-на-Дону → Богураев
👥 3 чел · 💰 4 000 ₽
🚗 Класс: Стандарт
ℹ ж/д вокзал, ребёнок 4 года""",
     dict(from_city="Ростов-на-Дону", to_city="Богураев", price=4000, passengers=3,
          urgent=True, car_class="Стандарт")),
]

NOT_ORDERS = [
    ("чат: Я", "Я"),
    ("чат: отдал", "Отдал, спасибо"),
    ("план работы", """Mercedes v-класса
План работы:
29.10.2026
Сочи-Ялта
31.10.2026
Ялта-Сочи
140.000 на руки
по заказу пока СТОП!!!"""),
    ("шаблон", "Здравствуйте! Возьму заказ 24.10 10:15 Ростов-на-Дону—Мариуполь 6 000 ₽"),
]


def run():
    bad = 0
    for name, text, expect in SAMPLES:
        o = parse_order(text)
        if o is None:
            print(f"FAIL {name}: None")
            bad += 1
            continue
        d = o.to_dict()
        errs = [f"{k}: ждали {v!r}, получили {d[k]!r}" for k, v in expect.items() if d[k] != v]
        print(("OK  " if not errs else "FAIL"), name, "" if not errs else "; ".join(errs))
        bad += bool(errs)
    for name, text in NOT_ORDERS:
        o = parse_order(text)
        print(("OK  " if o is None else "FAIL"), "не заказ:", name,
              "" if o is None else f"-> {o.from_city} / {o.to_city} / {o.price}")
        bad += o is not None
    print("\nПровалено:", bad)
    return bad


if __name__ == "__main__":
    raise SystemExit(run())
