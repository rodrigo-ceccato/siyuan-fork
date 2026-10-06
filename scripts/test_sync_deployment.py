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
import base64
import uuid


def main():
    source = Path(__file__).resolve().parents[1] / "deploy" / "sync"
    project = "siyuan-smoke-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="siyuan-sync-test-") as directory:
        root = Path(directory) / "sync"
        shutil.copytree(source, root, ignore=shutil.ignore_patterns(
            "secrets", "data", "borg", "borg-cache", "restore", ".env", ".backup.lock", "__pycache__"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, COMPOSE_PROJECT_NAME=project, SYNC_PORT=str(port),
                   SYNC_BIND_ADDRESS="127.0.0.1", BORG_DIRECTORY="./borg")
        compose = ["docker", "compose", "--project-directory", str(root), "-f", str(root / "compose.yml")]

        def run(args, check=True):
            return subprocess.run(args, cwd=root, env=env, check=check, capture_output=True, text=True)

        def request(method, path, data=None, auth=True):
            headers = {"Authorization": "Basic " + credential} if auth else {}
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read()

        try:
            run(["python3", "setup.py"])
            assert run(["python3", "setup.py"], check=False).returncode != 0
            passphrase = (root / "secrets/borg-passphrase").read_bytes()
            password = (root / "secrets/webdav-password").read_text().strip()
            credential = base64.b64encode(f"siyuan:{password}".encode()).decode()
            run(compose + ["config", "--quiet"])
            run(compose + ["up", "-d", "sync"])
            for attempt in range(30):
                try:
                    request("PROPFIND", "/")
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(1)
            else:
                raise RuntimeError("WebDAV did not become ready")
            try:
                request("GET", "/", auth=False)
                raise AssertionError("Unauthenticated request accepted")
            except urllib.error.HTTPError as error:
                assert error.code == 401
            request("MKCOL", "/main/")
            payload = b"opaque encrypted sync content\x00\xff"
            request("PUT", "/main/fixture", payload)
            assert request("GET", "/main/fixture")[1] == payload
            assert request("PROPFIND", "/main/")[0] == 207
            print("PASS: authentication and WebDAV MKCOL/PUT/GET/PROPFIND", flush=True)
            run(["python3", "backup.py"])
            archives = json.loads(run(compose + ["run", "--rm", "--no-deps", "backup", "list", "--json"]).stdout)["archives"]
            assert len(archives) == 1
            archive = archives[0]["name"]
            run(compose + ["run", "--rm", "--no-deps", "backup", "check", "--verify-data"])
            run(compose + ["run", "--rm", "--no-deps", "--workdir", "/restore", "backup", "extract", "::" + archive])
            assert (root / "restore/data/main/fixture").read_bytes() == payload
            assert (root / "restore/deployment/secrets/borg-passphrase").read_bytes() == passphrase
            assert (root / "restore/deployment/compose.yml").read_bytes() == (root / "compose.yml").read_bytes()
            assert not (root / "restore/deployment/borg").exists()
            assert request("GET", "/main/fixture")[1] == payload
            print("PASS: encrypted backup, integrity check, exact restore, and service restart", flush=True)
            shell = compose + ["run", "--rm", "--no-deps", "--entrypoint", "/bin/sh", "backup", "-c"]
            run(shell + ["cp /borg/repository/config /borg/config.original; printf 'invalid repository configuration' > /borg/repository/config"])
            before = run(shell + ["sha256sum /borg/repository/config"]).stdout
            result = run(["python3", "backup.py"], check=False)
            assert result.returncode != 0
            assert run(shell + ["sha256sum /borg/repository/config"]).stdout == before
            assert (root / "secrets/borg-passphrase").read_bytes() == passphrase
            assert request("GET", "/main/fixture")[1] == payload
            run(shell + ["cp /borg/config.original /borg/repository/config"])
            print("PASS: corrupt repository preserved and service restarted after failure", flush=True)
            run(compose + ["stop", "sync"])
            run(["python3", "backup.py"])
            assert not run(compose + ["ps", "--status", "running", "-q", "sync"]).stdout.strip()
            print("PASS: initially stopped service remains stopped", flush=True)
        except subprocess.CalledProcessError as error:
            print(error.stdout)
            print(error.stderr)
            raise
        except Exception:
            print(run(compose + ["logs", "--tail", "30", "sync"], check=False).stdout)
            raise
        finally:
            # 容器创建的恢复文件可能归 root 所有，使用同一工具镜像清理临时目录。
            run(compose + ["run", "--rm", "--no-deps", "--entrypoint", "/bin/sh", "backup",
                           "-c", "rm -rf /restore/* /borg/* /cache/*"], check=False)
            run(compose + ["down", "--volumes", "--remove-orphans"], check=False)


if __name__ == "__main__":
    main()
