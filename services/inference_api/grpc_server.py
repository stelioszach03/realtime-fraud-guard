from __future__ import annotations

import json
import os
import threading
from concurrent import futures
from typing import Any, Dict

import grpc
from loguru import logger

from model.inference_core import InferenceEngine


def _import_stubs():
    try:
        from services.inference_api.pb import fraud_pb2, fraud_pb2_grpc  # type: ignore
        return fraud_pb2, fraud_pb2_grpc
    except Exception as e:  # pragma: no cover
        logger.warning("grpc_stubs_import_failed: {}", e)
        return None, None


def _get_threshold() -> float:
    # Try to read live threshold from REST app if running in same process
    try:
        from services.inference_api.main import CURRENT_THRESHOLD  # type: ignore

        return float(CURRENT_THRESHOLD)
    except Exception:
        pass
    try:
        from services.inference_api.settings import get_settings

        st = get_settings()
        return float(os.getenv("SCORE_THRESHOLD", st.SCORE_THRESHOLD))
    except Exception:
        return float(os.getenv("SCORE_THRESHOLD", "0.85"))


def serve(port: int = 50051) -> None:
    fraud_pb2, fraud_pb2_grpc = _import_stubs()
    if fraud_pb2 is None or fraud_pb2_grpc is None:  # pragma: no cover
        logger.warning("grpc_disabled_no_stubs")
        return

    class FraudScoringServicer(fraud_pb2_grpc.FraudScoringServicer):  # type: ignore
        def __init__(self) -> None:
            self.engine = InferenceEngine()

        def Score(self, request, context):  # type: ignore
            try:
                payload: Dict[str, Any] = json.loads(request.payload_json or "{}")
            except Exception:
                payload = {}
            source = request.source or "payments"
            event_type = {"payments": "payment", "sms": "sms", "email": "email"}.get(source, "payment")
            prob, reasons, latency_ms = self.engine.score({"event_type": event_type, "event": payload})
            thr = _get_threshold()
            is_alert = bool(prob >= thr)
            return fraud_pb2.ScoreResponse(score=prob, is_alert=is_alert, threshold=thr, reasons=reasons[:3], latency_ms=latency_ms)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    fraud_pb2_grpc.add_FraudScoringServicer_to_server(FraudScoringServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("grpc_server_started port={}", port)
    server.wait_for_termination()


def run_in_thread(port: int = 50051) -> threading.Thread:
    t = threading.Thread(target=serve, args=(port,), daemon=True)
    t.start()
    return t


if __name__ == "__main__":  # pragma: no cover
    serve(int(os.getenv("GRPC_PORT", "50051")))
