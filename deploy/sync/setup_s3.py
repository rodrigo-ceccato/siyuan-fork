#!/usr/bin/env python3
import json
import os
from pathlib import Path
import secrets


def main():
    root = Path(__file__).resolve().parent
    data = root / "s3-data"
    if data.exists() and any(data.iterdir()):
        raise SystemExit("S3 data already exists; recover its credentials instead of generating new ones")
    directory = root / "secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / "s3.json"
    if path.exists():
        raise SystemExit("S3 credentials already exist; preserve them for access and recovery")
    # S3 凭据独立于数据仓库密钥和备份口令，初始化不覆盖任何现有凭据。
    config = {"identities": [{"name": "siyuan", "credentials": [{
        "accessKey": "siyuan-" + secrets.token_hex(12),
        "secretKey": secrets.token_urlsafe(32),
    }], "actions": ["Read:siyuan", "Write:siyuan", "List:siyuan", "Tagging:siyuan"]}]}
    with open(path, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
        json.dump(config, file, indent=2)
        file.write("\n")
    data.mkdir(mode=0o700, exist_ok=True)
    print("S3 credentials saved privately in secrets/s3.json; bucket: siyuan; region: us-east-1")


if __name__ == "__main__":
    main()
