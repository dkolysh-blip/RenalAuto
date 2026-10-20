from renalauto.customs import customs_fee_rub, duty_rub, low_util_applies, turnkey


def test_duty_by_age():
    # 3–5 лет, 1 600 см³: 2,5 €/см³
    assert duty_rub(1_500_000, 1600, "mid", 100) == 2.5 * 1600 * 100
    # старше 5 лет, 2 000 см³: 4,8 €/см³
    assert duty_rub(1_500_000, 2000, "old", 100) == 4.8 * 2000 * 100
    # до 3 лет: 48% от стоимости 20 000 € — больше минимума 5,5 €/см³
    assert duty_rub(2_000_000, 1600, "new", 100) == 0.48 * 2_000_000
    # дешёвая машина до 3 лет: 54%, но не меньше 2,5 €/см³
    assert duty_rub(500_000, 2000, "new", 100) == max(0.54 * 500_000, 2.5 * 2000 * 100)


def test_util_and_fee():
    assert low_util_applies("ice", 160, 3000) and not low_util_applies("ice", 161, 2000)
    assert not low_util_applies("ice", 150, 3500)
    assert low_util_applies("hybrid", 80, 1600) and not low_util_applies("ev", 150, 0)
    assert customs_fee_rub(1_500_000) == 11746 and customs_fee_rub(9_000_000) == 30000


def test_turnkey_totals():
    r = turnkey(price_rub=1_500_000, cc=1600, hp=150, age="mid", engine="ice", eur_rub=100, fee_rub=50_000)
    assert r.passable and r.total_is_from  # доставку и оформление назовёт менеджер
    assert r.total_rub == 1_500_000 + 400_000 + 5200 + 11746 + 50_000
    full = turnkey(price_rub=1_500_000, cc=1600, hp=150, age="mid", engine="ice", eur_rub=100, fee_rub=50_000,
                   logistics_rub=110_000, papers_rub=60_000)
    assert not full.total_is_from and full.total_rub == r.total_rub + 170_000
    bad = turnkey(price_rub=1_500_000, cc=1600, hp=200, age="mid", engine="ice", eur_rub=100, fee_rub=50_000,
                  logistics_rub=110_000, papers_rub=60_000)
    assert not bad.passable and bad.total_is_from and "160" in bad.verdict
