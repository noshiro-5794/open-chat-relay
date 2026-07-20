#!/usr/bin/env python3
import argparse
import secrets


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OpenChatRelay production secret values.")
    parser.add_argument(
        "--bytes",
        type=int,
        default=48,
        help="random bytes per generated secret before URL-safe encoding",
    )
    args = parser.parse_args()

    if args.bytes < 32:
        raise SystemExit("--bytes must be at least 32 for production secrets.")

    values = {
        "OPEN_CHAT_RELAY_JWT_SECRET_KEY": secrets.token_urlsafe(args.bytes),
        "OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN": secrets.token_urlsafe(args.bytes),
        "OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_SECRET": secrets.token_urlsafe(args.bytes),
        "OPEN_CHAT_RELAY_POSTGRES_PASSWORD": secrets.token_urlsafe(args.bytes),
        "OPEN_CHAT_RELAY_S3_SECRET_ACCESS_KEY": secrets.token_urlsafe(args.bytes),
    }
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
