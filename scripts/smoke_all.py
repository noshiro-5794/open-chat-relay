#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import urlparse, urlunparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpenChatRelay deployment smoke checks.")
    parser.add_argument(
        "--webtransport",
        action="store_true",
        help="also run WebTransport gateway and HTTP/3 runtime smoke checks",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("OPEN_CHAT_RELAY_DEPLOY_API_URL", "http://localhost:8000"),
        help="public API base URL",
    )
    parser.add_argument(
        "--console-url",
        default=os.environ.get("OPEN_CHAT_RELAY_DEPLOY_CONSOLE_URL", "http://localhost:5173"),
        help="console base URL; pass an empty value to skip console checks",
    )
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("OPEN_CHAT_RELAY_DEPLOY_GATEWAY_URL", ""),
        help="WebTransport gateway HTTP control-plane URL",
    )
    parser.add_argument(
        "--runtime-url",
        default=os.environ.get("OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL", ""),
        help="WebTransport HTTP/3 runtime URL used by the Node runtime smoke",
    )
    parser.add_argument(
        "--skip-realtime",
        action="store_true",
        help="skip WebSocket/Redis realtime smoke checks",
    )
    args = parser.parse_args()

    smoke_env = build_smoke_env(args)

    run_step("deployment check", [sys.executable, "scripts/check_deployment.py"], env=smoke_env)
    run_step("api smoke", [sys.executable, "scripts/smoke_api.py"], env=smoke_env)

    if not args.skip_realtime:
        run_step("realtime smoke", [sys.executable, "scripts/smoke_realtime.py"], env=smoke_env)
        run_step("presence smoke", [sys.executable, "scripts/smoke_presence.py"], env=smoke_env)
        run_step("typing smoke", [sys.executable, "scripts/smoke_typing.py"], env=smoke_env)

    if args.webtransport:
        run_step(
            "webtransport gateway smoke",
            [sys.executable, "scripts/smoke_webtransport_gateway.py"],
            env=smoke_env,
        )
        run_step(
            "webtransport runtime smoke",
            ["npm", "run", "smoke:runtime"],
            cwd="gateways/webtransport",
            env=smoke_env,
        )

    print("All requested smoke checks passed.")
    return 0


def build_smoke_env(args: argparse.Namespace) -> dict[str, str]:
    env = {
        **os.environ,
        "OPEN_CHAT_RELAY_DEPLOY_API_URL": args.api_url.rstrip("/"),
        "OPEN_CHAT_RELAY_DEPLOY_CONSOLE_URL": args.console_url.rstrip("/"),
        "OPEN_CHAT_RELAY_SMOKE_BASE_URL": args.api_url.rstrip("/"),
    }
    if args.gateway_url:
        gateway_url = args.gateway_url.rstrip("/")
        env["OPEN_CHAT_RELAY_DEPLOY_GATEWAY_URL"] = gateway_url
        env["OPEN_CHAT_RELAY_SMOKE_WEBTRANSPORT_GATEWAY_URL"] = gateway_url
    if args.runtime_url:
        env["OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL"] = args.runtime_url.rstrip("/")
    elif args.gateway_url:
        env["OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL"] = runtime_url_from_gateway_url(args.gateway_url)
    else:
        env["OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL"] = "https://127.0.0.1:8081/v1/wt"
    return env


def runtime_url_from_gateway_url(gateway_url: str) -> str:
    parsed = urlparse(gateway_url.rstrip("/"))
    scheme = "https" if parsed.scheme in {"http", "https"} else parsed.scheme
    return urlunparse((scheme, parsed.netloc, "/v1/wt", "", "", ""))


def run_step(
    label: str,
    command: Sequence[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    print(f"\n==> {label}")
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
