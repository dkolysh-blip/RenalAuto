from datetime import date

from renalauto.describe import describe
from renalauto.models import Listing
from renalauto.rates import Rates
from renalauto.view import car_view

RATES = Rates({"KRW": 0.058, "CNY": 11.2, "USD": 80})
TODAY = date(2026, 9, 29)


def view(title, **kw):
    base = dict(source="encar", external_id="1", country="KR", url="u", title=title, make="기아", model="K5",
                year=2022, mileage_km=45_000, price=20_000_000, currency="KRW", fuel="가솔린", transmission="오토",
                location="경기", extra={"displacement": "1,598cc", "color": "흰색"})
    base.update(kw)
    return car_view(Listing(**base), RATES)


def test_describe_model_trim_and_facts():
    d = describe(view("기아 K5 1.6 터보 노블레스"), today=TODAY)
    text = " ".join(d.paragraphs)
    assert "седан D-класса" in text and "Optima" in text
    assert "Комплектация Noblesse — высокая" in text and "сверит по VIN" in text
    assert "1.6 л турбо" in text and "Кёнгидо" in text
    assert {"Турбо", "Автомат", "Небольшой пробег"} <= set(d.highlights)
    assert d.meta.startswith("Kia K5 1.6 Turbo Noblesse 2022 года, седан D-класса")


def test_describe_non_passable_and_new_car():
    d = describe(view("현대 팰리세이드 HEV 2.5T 4WD 7인승 캘리그래피", make="현대", model="팰리세이드", year=2026,
                      mileage_km=31_958, fuel="하이브리드(가솔린)", extra={}), today=TODAY)
    text = " ".join(d.paragraphs)
    assert "не получится привезти" in text and "подберёт похожую" in text and "привезёт машину" not in text
    assert "интенсивная" not in text  # новой машине пробег в год не оцениваем
    assert "Полный привод" in d.highlights and "7 мест" in d.highlights


def test_describe_unknown_model_is_still_readable():
    d = describe(view("쉐보레 올란도 1.8", make="쉐보레", model="올란도", extra={}), today=TODAY)
    assert d.paragraphs[0].startswith("Chevrolet")
