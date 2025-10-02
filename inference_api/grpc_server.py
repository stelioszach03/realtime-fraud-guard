from __future__ import annotations

import json
import logging
from concurrent import futures

import grpc

from model.inference_core import InferenceEngine

try:
    from inference_api.pb import fraud_pb2, fraud_pb2_grpc  # type: ignore
except Exception as e:  # pragma: no cover
    fraud_pb2 = None
    fraud_pb2_grpc = None


class _BaseServicer:  # fallback when stubs not generated
    pass


BaseServicer = getattr(fraud_pb2_grpc, "FraudScoringServicer", _BaseServicer) if fraud_pb2_grpc else _BaseServicer


class FraudScoringServicer(BaseServicer):  # type: ignore
    def __init__(self) -> None:
        self.engine = InferenceEngine()

    def Score(self, request, context):  # type: ignore
        payload = json.loads(request.payload_json or "{}")
        proba, reasons, rule_hits, version = self.engine.predict_proba_and_reasons(request.event_type, payload)
        return fraud_pb2.ScoreResponse(
            id=request.id,
            risk_score=proba,
            reasons=reasons,
            rule_hits=rule_hits,
            model_version=version,
        )


def serve(port: int = 50051) -> None:
    if fraud_pb2 is None or fraud_pb2_grpc is None:  # pragma: no cover
        raise RuntimeError("gRPC stubs not generated. Run `make proto`." )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    fraud_pb2_grpc.add_FraudScoringServicer_to_server(FraudScoringServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logging.info("gRPC server started on port %d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
