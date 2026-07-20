#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local WebTransport certificate.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--out-dir", default="local/certs")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = out_dir / "webtransport.key"
    cert_path = out_dir / "webtransport.crt"
    subject_alt_name = (
        "subjectAltName=IP:{host}" if is_ip_address(args.host) else "subjectAltName=DNS:{host}"
    )

    subprocess.run(  # noqa: S603
        ["openssl", "ecparam", "-genkey", "-name", "prime256v1", "-out", str(key_path)],  # noqa: S607
        check=True,
    )
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "openssl",
            "req",
            "-x509",
            "-new",
            "-key",
            str(key_path),
            "-out",
            str(cert_path),
            "-subj",
            f"/CN={args.host}",
            "-addext",
            subject_alt_name.format(host=args.host),
            "-days",
            str(args.days),
        ],
        check=True,
    )

    print(f"Wrote {cert_path}")
    print(f"Wrote {key_path}")
    return 0


def is_ip_address(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


if __name__ == "__main__":
    raise SystemExit(main())
