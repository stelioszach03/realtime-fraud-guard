from __future__ import annotations

import math
import os
import time
from typing import Dict, List, Tuple

import numpy as np

from features.featurizer import featurize
from model.registry import load_latest_model
from services.rules.engine import evaluate as eval_rules, combine_score
from services.rules.reasons import build_reasons


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _top_k_explanations_k() -> int:
    try:
        return int(os.getenv("TOP_K_EXPLANATIONS", "3"))
    except Exception:
        return 3


class InferenceEngine:
    def __init__(self) -> None:
        model, version, feature_names, meta = load_latest_model()
        self.model = model
        self.model_version = version
        self.feature_names = feature_names
        self.meta = meta

    def _align_vector(self, vec: List[float], names: List[str]) -> List[float]:
        if not self.feature_names:
            return vec
        name_to_val = {n: v for n, v in zip(names, vec)}
        return [float(name_to_val.get(n, 0.0)) for n in self.feature_names]

    def _model_top_reasons(self, vec: List[float], names: List[str]) -> List[str]:
        k = _top_k_explanations_k()
        if self.model is None:
            return []
        try:
            # sklearn Pipeline with LogisticRegression named 'clf'
            from sklearn.pipeline import Pipeline  # type: ignore
            from sklearn.linear_model import LogisticRegression  # type: ignore

            if isinstance(self.model, Pipeline):
                steps = dict(self.model.named_steps)
                clf = steps.get("clf")
                if isinstance(clf, LogisticRegression):
                    # transform features with preceding steps
                    X = np.array([vec])
                    Xt = self.model[:-1].transform(X) if len(self.model.steps) > 1 else X
                    coef = clf.coef_[0]
                    contrib = np.abs(coef * Xt[0])
                    idx = np.argsort(contrib)[-k:][::-1]
                    return [names[i] if i < len(names) else f"f{i}" for i in idx]
        except Exception:
            pass

        # Try XGBoost explainer using pred_contribs
        try:
            from xgboost import DMatrix

            # sklearn XGBClassifier has get_booster()
            booster = getattr(self.model, "get_booster", lambda: None)()
            if booster is not None:
                X = np.array([vec], dtype=float)
                contrib = booster.predict(DMatrix(X), pred_contribs=True)[0]  # includes bias at end
                contrib = np.abs(contrib[:-1])  # strip bias
                idx = np.argsort(contrib)[-k:][::-1]
                return [names[i] if i < len(names) else f"f{i}" for i in idx]
        except Exception:
            pass

        # Fallback: global feature names (truncate)
        return names[:k]

    def score(self, event_json: Dict) -> Tuple[float, List[str], float]:
        """Score a single event json of shape {event_type, event}.

        Returns (probability, top_reasons, latency_ms).
        """
        start = time.perf_counter()
        event_type = event_json.get("event_type")
        event = event_json.get("event", {})
        vec, names = featurize(event_type, event)
        if self.model is not None:
            X = [self._align_vector(vec, names)]
            prob = float(self.model.predict_proba(X)[0][1])
            rule_res = eval_rules(event_type, event)
            prob = combine_score(prob, rule_res)
            reasons = self._model_top_reasons(vec, names)
        else:
            # heuristic
            if event_type == "payment":
                amount = float(event.get("amount", 0.0))
                merchant_risk = vec[1] if len(vec) > 1 else 0.0
                prob = float(_sigmoid(0.003 * amount + 2.0 * (merchant_risk - 0.5)))
                reasons = ["amount", "merchant_risk"]
            elif event_type == "sms":
                text_len = vec[0] if vec else 0.0
                url_count = vec[1] if len(vec) > 1 else 0.0
                word_hits = vec[2] if len(vec) > 2 else 0.0
                prob = float(_sigmoid(0.02 * url_count + 0.5 * word_hits + 0.001 * max(0.0, text_len - 140)))
                reasons = ["url_count", "suspicious_word_hits"]
            elif event_type == "email":
                link_count = vec[2] if len(vec) > 2 else 0.0
                sender_domain_risk = vec[3] if len(vec) > 3 else 0.0
                prob = float(_sigmoid(0.5 * link_count + 2.0 * (sender_domain_risk - 0.5)))
                reasons = ["link_count", "sender_domain_risk"]
            else:
                prob = 0.05
                reasons = []
        latency_ms = (time.perf_counter() - start) * 1000.0
        reasons = reasons[:_top_k_explanations_k()]
        return prob, reasons, latency_ms

    def predict_proba_and_reasons(self, event_type: str, event: Dict) -> Tuple[float, List[str], List[str], str]:
        vec, names = featurize(event_type, event)
        # Model path
        if self.model is not None:
            X = [self._align_vector(vec, names)]
            proba = float(self.model.predict_proba(X)[0][1])
            model_reasons = self._model_top_reasons(vec, names)
            rule_res = eval_rules(event_type, event)
            combined = combine_score(proba, rule_res)
            # Prioritize rule reasons to ensure they surface
            reasons = (rule_res.reasons + model_reasons)[:_top_k_explanations_k()]
            return combined, reasons, rule_res.hits, self.model_version

        # Heuristic fallback by event type
        reasons: List[str] = []
        rule_res = eval_rules(event_type, event)
        reasons.extend(rule_res.reasons)

        if event_type == "payment":
            amount = float(event.get("amount", 0.0))
            merchant_risk = vec[1] if len(vec) > 1 else 0.0
            score = _sigmoid(0.003 * amount + 2.0 * (merchant_risk - 0.5))
            if amount > 500:
                reasons.append("high_amount")
            return float(score), reasons, rule_res.hits, "heuristic"
        if event_type == "sms":
            text_len = vec[0] if vec else 0.0
            url_count = vec[1] if len(vec) > 1 else 0.0
            word_hits = vec[2] if len(vec) > 2 else 0.0
            score = _sigmoid(0.02 * url_count + 0.5 * word_hits + 0.001 * max(0.0, text_len - 140))
            if word_hits >= 2:
                reasons.append("suspicious_words")
            return float(score), reasons, rule_res.hits, "heuristic"
        if event_type == "email":
            link_count = vec[2] if len(vec) > 2 else 0.0
            sender_domain_risk = vec[3] if len(vec) > 3 else 0.0
            score = _sigmoid(0.5 * link_count + 2.0 * (sender_domain_risk - 0.5))
            if link_count >= 1:
                reasons.append("contains_links")
            return float(score), reasons, rule_res.hits, "heuristic"

        return 0.05, reasons, rule_hits, "heuristic"
