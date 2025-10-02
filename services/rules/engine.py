from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from features.transformers import STATS
from services.rules.reasons import build_reasons


URL_RE = re.compile(r"https?://([^/\s]+)", re.I)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Simple last-seen state to detect new_device and geo distance per user
_LAST_DEVICE: Dict[str, str] = {}
_LAST_GEO: Dict[str, Tuple[float, float, float]] = {}  # user_id -> (lat, lon, ts)


@dataclass
class RuleResult:
    hits: List[str]
    reasons: List[str]
    boost_score: float
    hard: bool


def _extract_domain(text: str) -> Optional[str]:
    m = URL_RE.search(text or "")
    if not m:
        return None
    host = m.group(1).lower()
    return host


def _new_device(user_id: Optional[str], device_id: Optional[str]) -> bool:
    if not user_id or not device_id:
        return False
    prev = _LAST_DEVICE.get(user_id)
    is_new = prev is not None and prev != device_id
    _LAST_DEVICE[user_id] = device_id
    return is_new


def _geo_distance(user_id: Optional[str], lat: Optional[float], lon: Optional[float], now: float) -> Tuple[float, Optional[float]]:
    if user_id is None or lat is None or lon is None:
        return 0.0, None
    prev = _LAST_GEO.get(user_id)
    dist = 0.0
    dt = None
    if prev:
        plat, plon, pts = prev
        dist = _haversine_km(plat, plon, lat, lon)
        dt = now - pts
    _LAST_GEO[user_id] = (lat, lon, now)
    return dist, dt


def evaluate(event_type: str, event: Dict, *, now: Optional[float] = None) -> RuleResult:
    now = now or time.time()
    user_id = event.get("user_id")
    device_id = event.get("device_id")
    country = event.get("country")
    lat = event.get("city_lat")
    lon = event.get("city_lon")

    hits: List[str] = []
    ctx: Dict = {}
    hard = False
    boost = 0.0

    # Velocity rule (2m window)
    if user_id:
        cnt_2m = STATS.get_user(user_id).count_in_window(120, now)
        ctx["velocity_count"] = cnt_2m
        ctx["velocity_window_min"] = 2
        if cnt_2m >= 7:
            hits.append("velocity_high")
            boost = max(boost, 0.8)

    # Geo + device + amount conjunctive rule
    amount = float(event.get("amount", 0.0)) if event_type == "payment" else 0.0
    amount_thr = 1000.0
    is_new_dev = _new_device(user_id, device_id)
    dist_km, dt = _geo_distance(user_id, lat, lon, now)
    ctx.update({"amount_threshold": amount_thr, "geo_distance_km": dist_km, "new_device": is_new_dev})
    if event_type == "payment" and amount > amount_thr and is_new_dev and dist_km > 500.0:
        hits.extend(["amount_large", "new_device", "geo_distance_large"])
        boost = max(boost, 0.9)
        # If travel is physically impossible in the elapsed time, mark hard
        if dt and dt > 0:
            speed = dist_km / (dt / 3600.0)
            if speed > 1000.0:
                hits.append("geo_impossible")
                hard = True

    # SMS: phishing + fresh domain
    if event_type == "sms":
        text = str(event.get("text", event.get("message_text", "")))
        domain = _extract_domain(text)
        if domain is not None:
            age_days = int(event.get("domain_age_days", event.get("link_domain_age_days", 9999)))
            ctx["domain_age_days"] = age_days
            if age_days < 30:
                hits.append("sms_phishing_link_fresh_domain")
                boost = max(boost, 0.85)

    # Email auth failures
    if event_type == "email":
        spf_fail = bool(event.get("spf_fail", False) or (event.get("spf_pass") is False))
        dmarc_fail = bool(event.get("dmarc_fail", False) or (event.get("dmarc_pass") is False))
        if spf_fail or dmarc_fail:
            hits.append("email_spf_dmarc_fail")
            boost = max(boost, 0.95)
            # If both fail, consider a hard flag
            if spf_fail and dmarc_fail:
                hard = True

    reasons = build_reasons(hits, ctx)
    return RuleResult(hits=hits, reasons=reasons, boost_score=boost, hard=hard)


def combine_score(model_proba: float, res: RuleResult) -> float:
    if res.hard:
        return 1.0
    return max(model_proba, res.boost_score)
