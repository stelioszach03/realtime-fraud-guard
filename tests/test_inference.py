import numpy as np

from model.inference_core import InferenceEngine


class DummyModel:
    def predict_proba(self, X):
        # return low probability for class 1 consistently
        return np.array([[0.8, 0.2] for _ in range(len(X))])


def test_model_rules_merge_and_hard_flag(monkeypatch):
    engine = InferenceEngine()
    # inject dummy model
    engine.model = DummyModel()
    engine.model_version = "test"

    # Trigger email rule hard flag (SPF+DMARC fails)
    score, reasons, rule_hits, version = engine.predict_proba_and_reasons(
        "email",
        {"user_id": "u", "subject": "Notice", "body": "hi", "sender_domain": "a.b", "spf_fail": True, "dmarc_fail": True},
    )
    assert score == 1.0  # hard flag elevates to 1.0
    # reasons include model features and rule rationale
    assert any(r in reasons for r in ["subject_len", "body_len", "link_count", "sender_domain_risk"])
    assert any("SPF/DMARC" in r for r in reasons)
    assert isinstance(version, str)
