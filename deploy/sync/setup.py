#!/usr/bin/env python3
import argparse
import base64
import hashlib
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description="Initialize private sync credentials without overwriting existing keys")
    parser.add_argument("--username", default="siyuan")
    args = parser.parse_args()
    if not args.username or any(c in args.username for c in ":\r\n"):
        parser.error("Username must not be empty or contain colons or newlines")
    root = Path(__file__).resolve().parent
    directory = root / "secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    paths = [directory / name for name in ("webdav.htpasswd", "webdav-password", "borg-passphrase")]
    if any(path.exists() for path in paths):
        parser.error("Credentials already exist; preserve them for access and recovery")
    password = secrets.token_urlsafe(32)
    # 随机高熵密码使用标准 htpasswd 格式，明文凭据仅保存在权限受限的文件中。
    digest = base64.b64encode(hashlib.sha1(password.encode()).digest()).decode()
    values = [f"{args.username}:{{SHA}}{digest}\n", password + "\n", secrets.token_urlsafe(48) + "\n"]
    for path, value in zip(paths, values):
        with path.open("x", encoding="utf-8") as file:
            path.chmod(0o600)
            file.write(value)
    for name in ("data", "borg", "borg-cache", "restore"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    environment = root / ".env"
    template = environment.read_text(encoding="utf-8") if environment.exists() else (root / ".env.example").read_text(encoding="utf-8")
    lines = [line for line in template.splitlines() if not line.startswith(("SYNC_UID=", "SYNC_GID="))]
    environment.write_text("\n".join(lines) + f"\nSYNC_UID={os.getuid()}\nSYNC_GID={os.getgid()}\n", encoding="utf-8")
    environment.chmod(0o600)
    print(f"WebDAV username: {args.username}")
    print("Password: read secrets/webdav-password on this host")
    print("Copy secrets/borg-passphrase to independent secure storage before making backups")


if __name__ == "__main__":
    main()
