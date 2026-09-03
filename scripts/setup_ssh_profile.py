from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paper_repro_app.app import parse_ssh_target, write_ssh_profile


def parse_command(raw_command: str) -> dict[str, str]:
    value = (raw_command or "").strip()
    if not value:
        return {}
    return parse_ssh_target(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a reusable SSH config alias for cloud remote access.")
    parser.add_argument("--alias", default="papercloud", help="SSH alias name stored in ~/.ssh/config")
    parser.add_argument("--host", help="Remote host, e.g. connect.cqa1.seetacloud.com")
    parser.add_argument("--user", default="root", help="Remote login user")
    parser.add_argument("--port", default="22", help="SSH port")
    parser.add_argument("--key", default="~/.ssh/id_ed25519", help="Private key path or pasted key content")
    parser.add_argument("--ssh-command", help="Optional raw SSH command, e.g. ssh -p 12680 root@host -i ~/.ssh/id_rsa")
    parser.add_argument("--force", action="store_true", help="Replace existing matching Host block")
    args = parser.parse_args()

    parsed = {}
    if args.ssh_command:
        parsed = parse_command(args.ssh_command)

    host = args.host or parsed.get("host")
    user = args.user or parsed.get("user")
    port = args.port or parsed.get("port")
    key = args.key or parsed.get("key")

    if not host:
        parser.error("Missing remote host. Provide --host or --ssh-command.")

    config_path = Path.home() / ".ssh" / "config"
    written_path = write_ssh_profile(args.alias, host, user, port, key, config_path=config_path, force=args.force)
    print(f"SSH profile written to: {written_path}")
    print(f"You can connect via: ssh {args.alias}")
    print("Tip: keep the private key in ~/.ssh and never commit it into Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
