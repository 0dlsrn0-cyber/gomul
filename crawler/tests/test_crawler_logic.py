"""크롤러 순수 로직 테스트 — 단위 환산 + LME 실시세/폴백 판정."""

import crawler


def test_usd_per_ton_to_krw_per_kg():
    # 13,190 USD/톤 × 1400원 / 1000 = KRW/kg
    assert crawler.usd_per_ton_to_krw_per_kg(13190.0, 1400.0) == round(13190.0 * 1400 / 1000)


def test_usd_per_oz_to_krw_per_kg():
    # troy oz → kg
    expected = round(2400.0 * 1400 / 0.0311034768)
    assert crawler.usd_per_oz_to_krw_per_kg(2400.0, 1400.0) == expected


def test_lme_real_keys_marks_fallback_inputs():
    yahoo = {"usd_krw": 1400.0, "gold_oz": 2400.0}

    # 정상: 비철 실시세(nonferrous ok) + 금 실시세(폴백 아님) → 둘 다 real
    lme, real = crawler.lme_to_krw_kg({"copper": 13000.0}, yahoo, set(), True)
    assert "copper" in lme and "copper" in real
    assert "gold" in lme and "gold" in real

    # 금 oz가 폴백 → 값은 있지만 real 아님(배지/누적 제외 대상)
    _, real_gfb = crawler.lme_to_krw_kg({"copper": 13000.0}, yahoo, {"gold_oz"}, True)
    assert "gold" not in real_gfb
    assert "copper" in real_gfb

    # nonferrous 다운 → 비철 real 아님
    _, real_nfdown = crawler.lme_to_krw_kg({"copper": 13000.0}, yahoo, set(), False)
    assert "copper" not in real_nfdown

    # 환율이 폴백 → 환산값 신뢰 불가, 전부 real 아님
    _, real_krwfb = crawler.lme_to_krw_kg({"copper": 13000.0}, yahoo, {"usd_krw"}, True)
    assert real_krwfb == set()
