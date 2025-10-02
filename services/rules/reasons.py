from __future__ import annotations

from typing import Dict, List


def build_reasons(hits: List[str], ctx: Dict) -> List[str]:
    reasons: List[str] = []
    # Velocity
    if "velocity_high" in hits:
        cnt = int(round(ctx.get("velocity_count", 0)))
        win = int(ctx.get("velocity_window_min", 2))
        reasons.append(f"velocity: {cnt} txn in {win}m")
    # Device
    if "new_device" in hits:
        reasons.append("device mismatch")
    # Geo
    if "geo_distance_large" in hits or "geo_impossible" in hits:
        dist = float(ctx.get("geo_distance_km", 0.0))
        reasons.append("geo impossible travel" if "geo_impossible" in hits else f"geo shift {dist:.0f}km")
    # Phishing link domain age
    if "sms_phishing_link_fresh_domain" in hits:
        days = int(ctx.get("domain_age_days", -1))
        if days >= 0:
            reasons.append(f"phishing link domain_age={days}d")
        else:
            reasons.append("phishing link")
    # Email auth failures
    if "email_spf_dmarc_fail" in hits:
        reasons.append("email auth failure (SPF/DMARC)")

    # Amount threshold
    if "amount_large" in hits:
        thr = float(ctx.get("amount_threshold", 0.0))
        reasons.append(f"high amount > {thr:.0f}")

    return reasons

