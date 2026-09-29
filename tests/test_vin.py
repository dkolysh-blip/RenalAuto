from renalauto.vin.decoder import compute_check_digit, decode, model_year_candidates


def test_known_valid_check_digits():
    assert compute_check_digit("1HGCM82633A004352") == "3"
    assert compute_check_digit("11111111111111111") == "1"


def test_decode_valid_chinese_vin():
    d = decode("LGXCE4CB8N0012345")
    assert d.valid_format and not d.errors
    assert d.country == "Китай"
    assert d.manufacturer == "BYD"
    assert d.check_digit.valid and d.check_digit.mandatory
    assert d.model_year == 2022


def test_chinese_vin_with_bad_check_digit_is_error():
    d = decode("LGXCE4CB0N0012345")
    assert d.valid_format
    assert any("Контрольный знак" in e for e in d.errors)


def test_korean_vin_bad_check_digit_is_only_warning():
    d = decode("KMHLM41CBMU123457")
    assert not d.errors
    assert d.manufacturer == "Hyundai"
    assert d.country == "Южная Корея"
    assert any("Контрольный знак" in w for w in d.warnings)
    assert d.model_year == 2021


def test_normalization_and_forbidden_letters():
    assert decode(" kmhlm41c6-mu123457 ").vin == "KMHLM41C6MU123457"
    d = decode("KMHLM41C6MU12345O")
    assert not d.valid_format
    assert "O" in d.errors[0]
    assert not decode("SHORT").valid_format


def test_model_year_with_hint():
    assert model_year_candidates("A", max_year=2027) == [1980, 2010]
    assert decode("KMHLM41C6AU123457").model_year == 2010
    assert model_year_candidates("Y", max_year=2027) == [2000]
    assert decode("KMHLM41C6MU123457", year_hint=1991).model_year == 1991
