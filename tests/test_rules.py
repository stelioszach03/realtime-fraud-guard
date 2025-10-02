from services.rules.engine import evaluate
from features.transformers import STATS


def test_payment_conjunctive_rule_and_reasons():
    # Seed a baseline device/geo for user uX
    u = "uX"
    t0 = 2_000_000.0
    # prime last state by evaluating a benign event at (lat, lon)
    evaluate(
        "payment",
        {
            "user_id": u,
            "device_id": "dev1",
            "city_lat": 37.7749,
            "city_lon": -122.4194,
            "amount": 10,
        },
        now=t0,
    )

    # Now large amount, new device, far geo within 1 minute
    res = evaluate(
        "payment",
        {
            "user_id": u,
            "device_id": "dev2",
            "city_lat": 51.5074,  # London
            "city_lon": -0.1278,
            "amount": 2000,
        },
        now=t0 + 60,
    )
    assert any(h in res.hits for h in ["amount_large", "new_device", "geo_distance_large"])  # all likely
    assert res.boost_score >= 0.9
    assert any("geo" in r or "device" in r for r in res.reasons)


def test_sms_phishing_and_email_auth_rules():
    sms = evaluate(
        "sms",
        {"user_id": "u2", "device_id": "d", "message_text": "visit http://bit.ly/abc", "domain_age_days": 5},
    )
    assert "sms_phishing_link_fresh_domain" in sms.hits
    assert any("phishing" in r for r in sms.reasons)

    email = evaluate("email", {"user_id": "u3", "spf_fail": True, "dmarc_fail": True})
    assert "email_spf_dmarc_fail" in email.hits
    assert any("SPF/DMARC" in r for r in email.reasons)


def test_velocity_rule_2m_window():
    u = "uV"
    # record 7 payments within 2 minutes in STATS
    base = 3_000_000.0
    for i in range(7):
        STATS.get_user(u).record_payment(5.0, "m1", "US", "dev1", now=base + i * 15)
    res = evaluate("payment", {"user_id": u, "device_id": "dev1", "amount": 1.0}, now=base + 120)
    assert "velocity_high" in res.hits
    assert any("velocity" in r for r in res.reasons)
