PYTHON ?= python3

.PHONY: install dev-api dev-consumer proto compose-up compose-down topics run-generator test train eval drift seed smoke test-docker all-up

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -r requirements.txt

dev-api:
	uvicorn services.inference_api.main:app --host 0.0.0.0 --port 8000 --reload

dev-consumer:
	$(PYTHON) -m services.inference_api.kafka_consumer

grpc:
	$(PYTHON) services/inference_api/grpc_server.py

proto:
	$(PYTHON) -m grpc_tools.protoc -I protos \
		--python_out=services/inference_api/pb --grpc_python_out=services/inference_api/pb \
		protos/fraud.proto
	@$(PYTHON) -c "p='services/inference_api/pb/fraud_pb2_grpc.py';import io,sys; s=open(p,'r',encoding='utf-8').read(); s=s.replace('import fraud_pb2 as','from . import fraud_pb2 as'); open(p,'w',encoding='utf-8').write(s); print('Patched',p)"

train:
	$(PYTHON) -m services.model.train --data evaluation/datasets/sample.jsonl --out models/

eval:
	$(PYTHON) -m evaluation.offline_eval --data evaluation/datasets/sample.jsonl

drift:
	$(PYTHON) -m evaluation.drift --ref evaluation/datasets/sample.jsonl --cur evaluation/datasets/sample.jsonl

compose-up:
	docker compose --env-file .env up -d --build

compose-down:
	docker compose down -v

topics:
	bash scripts/bootstrap_topics.sh

run-generator:
	STREAM?=payments
	RPS?=2
	$(PYTHON) -m services.generator.cli --stream $(STREAM) --rps $(RPS)

test:
	pytest -q

seed:
	$(PYTHON) -m scripts.load_sample_dataset

smoke:
	bash scripts/smoke.sh

test-docker:
	docker compose exec api pytest -q

all-up:
	make compose-up && make test-docker || true && make smoke
