from __future__ import annotations

from typing import Dict, List


REASONS = {
    "amount_gt_1000": "Amount exceeds threshold",
    "velocity_txn_gt_5_1m": "High transaction velocity in 1m",
    "foreign_country": "Transaction from foreign country",
    "suspicious_terms": "SMS contains suspicious terms",
    "has_links": "Email contains links",
    "high_amount": "High amount heuristic",
    "suspicious_words": "Multiple suspicious words",
    "contains_links": "Contains links",
}


def reasons_for_rules(rule_hits: List[str], event: Dict) -> List[str]:
    return [REASONS.get(r, r) for r in rule_hits]

