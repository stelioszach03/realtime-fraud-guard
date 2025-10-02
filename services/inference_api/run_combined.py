from __future__ import annotations

import os
import threading

import uvicorn
from loguru import logger

from services.inference_api.grpc_server import run_in_thread
from services.inference_api.main import app


def main() -> None:
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))
    http_host = os.getenv("API_HOST", "0.0.0.0")
    http_port = int(os.getenv("API_PORT", "8000"))

    # Run FastAPI (blocking) and start gRPC in background after startup log
    try:
        t = run_in_thread(grpc_port)
        logger.info("grpc_thread_launched port={}", grpc_port)
    except Exception as e:
        logger.warning("grpc_launch_failed: {}", e)

    uvicorn.run(app, host=http_host, port=http_port)


if __name__ == "__main__":
    main()
