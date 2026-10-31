from types import SimpleNamespace as NS

from accept import dm_text, dm_url, find_take_button, is_dm_only, wants_dm
from order_parser import parse_order

bad = 0


def check(name, got, want):
    global bad
    ok = got == want
    bad += not ok
    print("OK  " if ok else "FAIL", name, "" if ok else f"ждали {want!r}, получили {got!r}")


check("«в личку»", wants_dm("00:40 Ростов ЖД Таганрог\n2000р\nВ личку"), True)
check("«лс»", wants_dm("Ростов - Москва 9000 пишите в лс"), True)
check("без «в личку»", wants_dm("Ростов - Москва 9000"), False)
check("слово «лсу» не лс", wants_dm("Ростов - Москва 9000 по лсу"), False)

check("исключение по username", is_dm_only(-1001, "transferRostOBL", ["transferrostobl"]), True)
check("исключение по @ и регистру", is_dm_only(-1001, "TransferRostObl", ["@TransferRostOBL"]), True)
check("исключение по id", is_dm_only(-1001, None, [-1001]), True)
check("другая группа", is_dm_only(-1002, "other", ["transferrostobl"]), False)
check("нет username", is_dm_only(-1002, None, ["transferrostobl"]), False)

rows = [[NS(text="🔗 Источник"), NS(text="ВЗЯТЬ ЗАКАЗ")], [NS(text="Скрыть")]]
r = find_take_button(rows)
check("кнопка «Взять заказ»", (r[0], r[1]) if r else None, (0, 1))
check("кнопка «ЗАПРОСИТЬ»", find_take_button([[NS(text="ЗАПРОСИТЬ")]])[:2], (0, 0))
check("нет подходящей кнопки", find_take_button([[NS(text="Источник"), NS(text="Скрыть")]]), None)
check("нет кнопок", find_take_button(None), None)

o = parse_order("17.00 из Ростова в Таганрог 2000р в личку")
check("текст диспетчеру", dm_text(o), "Здравствуйте! Беру заказ: Ростов-на-Дону → Таганрог, 17:00, 2 000 ₽.")
o2 = parse_order("Сейчас Ростов - Москва 9000")
check("срочный заказ", dm_text(o2), "Здравствуйте! Беру заказ: Ростов-на-Дону → Москва, срочно, 9 000 ₽.")
check("ссылка", dm_url("@ivan_p", o).startswith("https://t.me/ivan_p?text=%D0%97%D0%B4%D1%80%D0%B0%D0%B2"), True)
print("\nПровалено:", bad)
raise SystemExit(bad)
