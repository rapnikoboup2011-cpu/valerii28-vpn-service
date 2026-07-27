def test_tariffs_load_stars_prices_from_env(monkeypatch):
    monkeypatch.setenv("PRICE_1_MONTH_STARS", "80")
    monkeypatch.setenv("PRICE_3_MONTHS_STARS", "210")
    monkeypatch.setenv("PRICE_12_MONTHS_STARS", "680")

    from bot.config import Config

    cfg = Config()

    assert cfg.tariff_by_code("1m").price_stars == 80
    assert cfg.tariff_by_code("3m").price_stars == 210
    assert cfg.tariff_by_code("12m").price_stars == 680
    assert cfg.tariff_by_code("nope") is None


def test_tariffs_default_to_spec_prices_without_env(monkeypatch):
    monkeypatch.delenv("PRICE_1_MONTH_STARS", raising=False)
    monkeypatch.delenv("PRICE_3_MONTHS_STARS", raising=False)
    monkeypatch.delenv("PRICE_12_MONTHS_STARS", raising=False)

    from bot.config import Config

    cfg = Config()

    assert cfg.tariff_by_code("1m").price_stars == 80
    assert cfg.tariff_by_code("3m").price_stars == 210
    assert cfg.tariff_by_code("12m").price_stars == 680
