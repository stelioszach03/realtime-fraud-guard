from __future__ import annotations

import argparse

from . import email_producer, payments_producer, sms_producer


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic stream generator")
    parser.add_argument("--topic", choices=["payments", "sms", "email"], help="Target stream/topic")
    # Back-compat: --stream
    parser.add_argument("--stream", choices=["payments", "sms", "email"], help=argparse.SUPPRESS)
    parser.add_argument("--rate", type=float, default=200.0, help="Target events per second")
    parser.add_argument("--rps", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--burst", action="store_true", help="Enable bursty sending")
    parser.add_argument("--fraud-ratio", type=float, default=0.03, help="Fraction of messages flagged as fraud")
    parser.add_argument("--kafka-broker", type=str, default=None, help="Kafka broker (e.g., PLAINTEXT://kafka:9092)")
    parser.add_argument("--max", type=int, default=None, help="Optional max events to send")
    args = parser.parse_args()

    stream = args.topic or args.stream
    if stream is None:
        parser.error("--topic is required")

    # Back-compat: if --rps provided, override --rate
    if getattr(args, "rps", None):
        args.rate = args.rps

    if stream == "payments":
        payments_producer.run(
            topic="payments",
            rate=args.rate,
            burst=args.burst,
            fraud_ratio=args.fraud_ratio,
            max_events=args.max,
            kafka_broker=args.kafka_broker,
        )
    elif stream == "sms":
        sms_producer.run(
            topic="sms",
            rate=args.rate,
            burst=args.burst,
            fraud_ratio=args.fraud_ratio,
            max_events=args.max,
            kafka_broker=args.kafka_broker,
        )
    else:
        email_producer.run(
            topic="email",
            rate=args.rate,
            burst=args.burst,
            fraud_ratio=args.fraud_ratio,
            max_events=args.max,
            kafka_broker=args.kafka_broker,
        )


if __name__ == "__main__":
    main()
