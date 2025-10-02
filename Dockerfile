FROM aegis-fraud-guard-base:latest AS base

FROM base AS builder
WORKDIR /app
COPY . /app
RUN make proto && mkdir -p /tmp/prom

FROM base
WORKDIR /app
COPY --from=builder /app /app
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN mkdir -p /tmp/prom
EXPOSE 8000 50051 9000
CMD ["python", "-m", "services.inference_api.run_combined"]
