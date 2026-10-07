#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import datetime
import hashlib
import hmac
import urllib.parse


def s3_request(endpoint, credentials, method, path, data=None, auth=True):
    payload = data if data is not None else b""
    body_hash = hashlib.sha256(payload).hexdigest()
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = date[:8]
    host = urllib.parse.urlsplit(endpoint).netloc
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{body_hash}\nx-amz-date:{date}\n"
    canonical = "\n".join((method, path, "", canonical_headers, signed_headers, body_hash))
    scope = day + "/us-east-1/s3/aws4_request"
    to_sign = "\n".join(("AWS4-HMAC-SHA256", date, scope, hashlib.sha256(canonical.encode()).hexdigest()))
    key = ("AWS4" + credentials["secretKey"]).encode()
    for part in (day, "us-east-1", "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {"x-amz-content-sha256": body_hash, "x-amz-date": date}
    if auth:
        headers["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={credentials['accessKey']}/{scope}, "
                                    f"SignedHeaders={signed_headers}, Signature={signature}")
    req = urllib.request.Request(endpoint + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=5) as response:
        return response.status, response.read()


def main():
    source = Path(__file__).resolve().parents[1] / "deploy" / "sync"
    project = "siyuan-smoke-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="siyuan-sync-test-") as directory:
        root = Path(directory) / "sync"
        shutil.copytree(source, root, ignore=shutil.ignore_patterns(
            "secrets", "data", "s3-data", "borg", "borg-cache", "restore", ".env", ".backup.lock", "__pycache__"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            s3_port = sock.getsockname()[1]
        env = dict(os.environ, COMPOSE_PROJECT_NAME=project,
                   S3_PORT=str(s3_port), SYNC_BIND_ADDRESS="127.0.0.1", BORG_DIRECTORY="./borg")
        compose = ["docker", "compose", "--project-directory", str(root), "-f", str(root / "compose.yml")]

        def run(args, check=True):
            return subprocess.run(args, cwd=root, env=env, check=check, capture_output=True, text=True)

        def wait_s3(path):
            for attempt in range(60):
                try:
                    return s3_request(endpoint, credentials, "GET", path)[1]
                except urllib.error.HTTPError as error:
                    if error.code not in (404, 500, 503):
                        raise
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    pass
                time.sleep(1)
            raise RuntimeError("S3 did not become ready")

        try:
            run(["python3", "setup.py"])
            assert run(["python3", "setup.py"], check=False).returncode != 0
            s3_config = (root / "secrets/s3.json").read_bytes()
            assert run(["python3", "setup_s3.py"], check=False).returncode != 0
            assert (root / "secrets/s3.json").read_bytes() == s3_config
            assert (root / "secrets/s3.json").stat().st_mode & 0o777 == 0o600
            saved_credentials = root / "secrets/s3.saved"
            (root / "secrets/s3.json").rename(saved_credentials)
            (root / "s3-data/existing-data").write_bytes(b"preserve existing S3 state")
            assert run(["python3", "setup_s3.py"], check=False).returncode != 0
            assert not (root / "secrets/s3.json").exists()
            assert (root / "s3-data/existing-data").read_bytes() == b"preserve existing S3 state"
            (root / "s3-data/existing-data").unlink()
            saved_credentials.rename(root / "secrets/s3.json")
            credentials = json.loads(s3_config)["identities"][0]["credentials"][0]
            endpoint = f"http://127.0.0.1:{s3_port}"
            passphrase = (root / "secrets/borg-passphrase").read_bytes()
            repo_key = b"isolated recovery fixture, not a real key\n"
            (root / "secrets/data-repo-key.txt").write_bytes(repo_key)
            run(compose + ["config", "--quiet"])
            run(compose + ["up", "-d", "s3"])
            payload = b"opaque encrypted sync content\x00\xff"
            (root / "data/main").mkdir()
            (root / "data/main/fixture").write_bytes(payload)
            wait_s3("/siyuan/")
            for auth_credentials, auth in ((credentials, False),
                                           (dict(credentials, secretKey="incorrect"), True)):
                try:
                    s3_request(endpoint, auth_credentials, "GET", "/siyuan/", auth=auth)
                    raise AssertionError("Invalid S3 authentication accepted")
                except urllib.error.HTTPError as error:
                    assert error.code == 403
            s3_request(endpoint, credentials, "PUT", "/siyuan/fixture", payload)
            assert wait_s3("/siyuan/fixture") == payload
            assert b"fixture" in s3_request(endpoint, credentials, "GET", "/siyuan/")[1]
            s3_request(endpoint, credentials, "PUT", "/siyuan/delete-fixture", payload)
            s3_request(endpoint, credentials, "DELETE", "/siyuan/delete-fixture")
            print("PASS: S3 signed PUT/GET/LIST/DELETE and rejected missing/incorrect credentials", flush=True)
            run(["python3", "backup.py"])
            archives = json.loads(run(compose + ["run", "--rm", "--no-deps", "backup", "list", "--json"]).stdout)["archives"]
            assert len(archives) == 1
            archive = archives[0]["name"]
            run(compose + ["run", "--rm", "--no-deps", "backup", "check", "--verify-data"])
            run(compose + ["run", "--rm", "--no-deps", "--workdir", "/restore", "backup", "extract", "::" + archive])
            assert (root / "restore/data/main/fixture").read_bytes() == payload
            assert (root / "restore/deployment/secrets/borg-passphrase").read_bytes() == passphrase
            assert (root / "restore/deployment/secrets/s3.json").read_bytes() == s3_config
            assert (root / "restore/deployment/secrets/data-repo-key.txt").read_bytes() == repo_key
            assert (root / "restore/s3-data").is_dir()
            assert (root / "restore/deployment/compose.yml").read_bytes() == (root / "compose.yml").read_bytes()
            assert not (root / "restore/deployment/borg").exists()
            assert wait_s3("/siyuan/fixture") == payload
            run(compose + ["stop", "s3"])
            (root / "s3-data").rename(root / "s3-original")
            shutil.copytree(root / "restore/s3-data", root / "s3-data")
            run(compose + ["up", "-d", "s3"])
            assert wait_s3("/siyuan/fixture") == payload
            print("PASS: encrypted backup, integrity check, exact restore, and service restart", flush=True)
            shell = compose + ["run", "--rm", "--no-deps", "--entrypoint", "/bin/sh", "backup", "-c"]
            run(shell + ["cp /borg/repository/config /borg/config.original; printf 'invalid repository configuration' > /borg/repository/config"])
            before = run(shell + ["sha256sum /borg/repository/config"]).stdout
            result = run(["python3", "backup.py"], check=False)
            assert result.returncode != 0
            assert run(shell + ["sha256sum /borg/repository/config"]).stdout == before
            assert (root / "secrets/borg-passphrase").read_bytes() == passphrase
            assert wait_s3("/siyuan/fixture") == payload
            run(shell + ["cp /borg/config.original /borg/repository/config"])
            print("PASS: corrupt repository preserved and service restarted after failure", flush=True)
            run(compose + ["stop", "s3"])
            run(["python3", "backup.py"])
            assert not run(compose + ["ps", "--status", "running", "-q", "s3"]).stdout.strip()
            assert not run(compose + ["ps", "--status", "running", "-q", "s3"]).stdout.strip()
            print("PASS: initially stopped service remains stopped", flush=True)
        except subprocess.CalledProcessError as error:
            print(error.stdout)
            print(error.stderr)
            raise
        except Exception:
            print(run(compose + ["logs", "--tail", "30", "s3"], check=False).stdout)
            raise
        finally:
            # 容器创建的恢复文件可能归 root 所有，使用同一工具镜像清理临时目录。
            run(compose + ["run", "--rm", "--no-deps", "--entrypoint", "/bin/sh", "backup",
                           "-c", "rm -rf /restore/* /borg/* /cache/*"], check=False)
            run(compose + ["down", "--volumes", "--remove-orphans"], check=False)


if __name__ == "__main__":
    main()
