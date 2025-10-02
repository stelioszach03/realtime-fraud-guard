from __future__ import annotations

from typing import Dict, List

from features.transformers import STATS


def _payment_rules(event: Dict) -> List[str]:
    hits: List[str] = []
    amount = float(event.get("amount", 0.0))
    user_id = str(event.get("user_id", ""))
    count_1m = STATS.get_user(user_id).txn_count_1m() if user_id else 0.0
    if amount > 1000:
        hits.append("amount_gt_1000")
    if count_1m > 5:
        hits.append("velocity_txn_gt_5_1m")
    if event.get("country") not in {"US", "CA", "GB", "DE", "AU"}:
        hits.append("foreign_country")
    return hits


def _sms_rules(event: Dict) -> List[str]:
    text = str(event.get("text", event.get("message_text", ""))).lower()
    hits: List[str] = []
    if any(w in text for w in ["verify", "password", "urgent", "click", "bank"]):
        hits.append("suspicious_terms")
    return hits


def _email_rules(event: Dict) -> List[str]:
    body = str(event.get("body", "")).lower()
    hits: List[str] = []
    if "http://" in body or "https://" in body:
        hits.append("has_links")
    return hits


def evaluate_rules(event_type: str, event: Dict) -> List[str]:
    if event_type == "payment":
        return _payment_rules(event)
    if event_type == "sms":
        return _sms_rules(event)
    if event_type == "email":
        return _email_rules(event)
    return []
