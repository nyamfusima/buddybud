from app.services.metrics import _r1, display_name, nps_of, osat_of, summarize
from app.services.taxonomy import keyword_classify, tenure_band


def test_nps_matches_v2_definition():
    # 3 promoters, 1 passive, 2 detractors over 6 -> (3-2)/6 = 16.666.. -> 16.7
    assert nps_of([10, 9, 9, 8, 6, 0]) == 16.7
    assert nps_of([None, None]) is None
    assert nps_of([10, 10]) == 100.0


def test_osat_is_top_box_share():
    assert osat_of([5, 5, 4, 3]) == 50.0
    assert osat_of([]) is None


def test_rounding_is_js_style():
    # JS Math.round rounds .5 up (towards +inf); Python's round() would give banker's rounding
    assert _r1(0.25) == 0.3
    assert _r1(-0.25) == -0.2


def test_summarize_counts_and_categories():
    payload = {
        "all_rows": [{"date": "2026-11-01", "nps": 10, "osat": 5}, {"date": "2026-11-02", "nps": 3, "osat": 2},
                     {"date": "2026-10-01", "nps": 0, "osat": 1}],
        "detractors": [{"date": "2026-11-02", "bucket": "People", "category": "Unaccommodating", "nps": 3, "comment": ""},
                       {"date": "2026-10-01", "bucket": "Process", "category": "Billing", "nps": 0, "comment": ""}],
    }
    s = summarize(payload, "2026-11-01", "2026-11-30")
    assert s["surveys"] == 2 and s["nps"] == 0.0 and s["promoters"] == 1 and s["detractors"] == 1
    assert s["categories"] == [{"bucket": "People", "category": "Unaccommodating", "count": 1, "pct": 100.0}]


def test_helpers():
    assert display_name("ANELISA TYEMELA") == "Anelisa T."
    assert tenure_band(10) == "0-30 days" and tenure_band(400) == "365+ days"
    assert keyword_classify("The agent was rude and hung up")[1] == "Unaccommodating"
    assert keyword_classify("")[0] == "None"
