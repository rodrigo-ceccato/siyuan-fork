#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import secrets
from setup_s3 import main as setup_s3


def main():
    parser = argparse.ArgumentParser(description="Initialize private sync credentials without overwriting existing keys")
    parser.parse_args()
    root = Path(__file__).resolve().parent
    directory = root / "secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    if any(directory.iterdir()) or ((root / "s3-data").exists() and any((root / "s3-data").iterdir())):
        parser.error("Credentials already exist; preserve them for access and recovery")
    # 备份口令独立生成，不覆盖已有仓库及恢复材料。
    with open(directory / "borg-passphrase", "x", encoding="utf-8",
              opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
        file.write(secrets.token_urlsafe(48) + "\n")
    for name in ("data", "borg", "borg-cache", "restore"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    environment = root / ".env"
    template = environment.read_text(encoding="utf-8") if environment.exists() else (root / ".env.example").read_text(encoding="utf-8")
    lines = [line for line in template.splitlines() if not line.startswith(("SYNC_UID=", "SYNC_GID="))]
    environment.write_text("\n".join(lines) + f"\nSYNC_UID={os.getuid()}\nSYNC_GID={os.getgid()}\n", encoding="utf-8")
    environment.chmod(0o600)
    setup_s3()
    print("Copy secrets/borg-passphrase to independent secure storage before making backups")


if __name__ == "__main__":
    main()
