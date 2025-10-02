from __future__ import annotations

import re
import time
from collections import deque
from hashlib import blake2b
from typing import Deque, Dict, List, Tuple

from .schema import FEATURE_VERSION
from .transformers import STATS


URL_RE = re.compile(r"https?://\S+", re.I)
SUSPICIOUS_WORDS = {"verify", "password", "urgent", "click", "bank"}

# Keep a small rolling log of recent meta for debugging/inspection
_RECENT_META: Deque[dict] = deque(maxlen=1000)


def _hash01(s: str) -> float:
    if not s:
        return 0.0
    h = blake2b(s.encode(), digest_size=4).digest()
    return int.from_bytes(h, "little") / 2**32


def _sms_has_link(text: str) -> bool:
    return bool(URL_RE.search(text or ""))


def _spoof_heuristic(sender_domain: str, subject: str, body: str) -> bool:
    text = f"{subject} {body}".lower()
    domain = (sender_domain or "").lower()
    if any(k in domain for k in ["-secure", "-support", "-verify"]):
        return True
    if any(w in text for w in ["verify", "password", "action required", "secure your account"]):
        return True
    if URL_RE.search(body or ""):
        return True
    return False


def featurize(event_type: str, event: Dict, with_meta: bool = False) -> Tuple[List[float], List[str]] | Tuple[List[float], List[str], Dict]:
    """Return (vector, feature_names[, meta]) from raw event.

    Uses in-memory stateful aggregations keyed by user_id and device_id.
    """
    now = time.time()
    user_id = str(event.get("user_id", "")) or None
    device_id = str(event.get("device_id", "")) or None
    country = event.get("country")

    meta = {
        "feature_version": FEATURE_VERSION,
        "event_type": event_type,
        "user_id": user_id,
        "device_id": device_id,
        "timestamp": now,
    }

    features: List[float] = []
    names: List[str] = []

    # Helper to read stats for user/device
    def user_stats():
        return STATS.get_user(user_id) if user_id else None

    def device_stats():
        return STATS.get_device(device_id) if device_id else None

    if event_type == "payment":
        amount = float(event.get("amount", 0.0))
        merchant = str(event.get("merchant", event.get("merchant_name", "")))
        merchant_id = str(event.get("merchant_id", "")) or None

        if user_id:
            STATS.get_user(user_id).record_payment(amount, merchant_id, country, device_id, now)
        if device_id:
            STATS.get_device(device_id).record_payment(amount, merchant_id, country, device_id, now)

        # Base
        features.extend([amount, _hash01(merchant)])
        names.extend(["amount", "merchant_risk"])

        # User stats
        us = user_stats()
        if us:
            features.extend([
                us.txn_count_1m(),
                us.txn_count_5m(),
                us.txn_count_1h(),
                us.sum_amount_1h(),
                us.avg_amount_24h(),
                us.unique_merchants_24h(),
                us.geo_switch_24h(),
                us.device_switch_24h(),
            ])
            names.extend([
                "txn_count_1m_user",
                "txn_count_5m_user",
                "txn_count_1h_user",
                "sum_amount_1h_user",
                "avg_amount_24h_user",
                "unique_merchants_24h_user",
                "geo_switch_24h_user",
                "device_switch_24h_user",
            ])

        # Device stats (subset)
        ds = device_stats()
        if ds:
            features.extend([
                ds.txn_count_1h(),
                ds.sum_amount_1h(),
            ])
            names.extend([
                "txn_count_1h_device",
                "sum_amount_1h_device",
            ])

    elif event_type == "sms":
        text = str(event.get("text", event.get("message_text", "")))
        text_len = len(text)
        url_count = len(URL_RE.findall(text))
        word_hits = sum(1 for w in SUSPICIOUS_WORDS if w in text.lower())
        has_link = _sms_has_link(text)

        if user_id:
            STATS.get_user(user_id).record_sms(has_link, country, device_id, now)
        if device_id:
            STATS.get_device(device_id).record_sms(has_link, country, device_id, now)

        features.extend([float(text_len), float(url_count), float(word_hits)])
        names.extend(["text_len", "url_count", "suspicious_word_hits"])

        us = user_stats()
        if us:
            features.append(us.sms_link_ratio_1h())
            names.append("sms_link_ratio_1h_user")
            features.append(us.device_switch_24h())
            names.append("device_switch_24h_user")
            features.append(us.geo_switch_24h())
            names.append("geo_switch_24h_user")

    elif event_type == "email":
        subject = str(event.get("subject", ""))
        body = str(event.get("body", ""))
        sender_domain = str(event.get("sender_domain", ""))
        link_count = len(URL_RE.findall(body))
        spoof = _spoof_heuristic(sender_domain, subject, body)

        if user_id:
            STATS.get_user(user_id).record_email(spoof, country, device_id, now)
        if device_id:
            STATS.get_device(device_id).record_email(spoof, country, device_id, now)

        features.extend([
            float(len(subject)),
            float(len(body)),
            float(link_count),
            _hash01(sender_domain),
        ])
        names.extend(["subject_len", "body_len", "link_count", "sender_domain_risk"])

        us = user_stats()
        if us:
            features.append(us.email_spoof_score_24h())
            names.append("email_spoof_score_24h_user")
            features.append(us.device_switch_24h())
            names.append("device_switch_24h_user")

    else:
        features = [0.0]
        names = ["bias"]

    if with_meta:
        _RECENT_META.append(meta)
        return features, names, meta
    return features, names

