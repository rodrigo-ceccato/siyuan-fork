#!/usr/bin/env python3
import fcntl
from pathlib import Path
import signal
import subprocess
import uuid


ROOT = Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "compose.yml")]


def run(*args, capture=False):
    return subprocess.run(COMPOSE + list(args), check=True, text=True, capture_output=capture)


def interrupted(signum, frame):
    raise RuntimeError(f"Backup interrupted by signal {signum}")


def main():
    # 主机负责停服与恢复，备份容器无需访问 Docker 控制接口。
    with (ROOT / ".backup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run("config", "--quiet")
        run("build", "backup")
        running = [service for service in ("s3",)
                   if run("ps", "--status", "running", "-q", service, capture=True).stdout.strip()]
        container = "siyuan-backup-" + uuid.uuid4().hex
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, interrupted)
        try:
            if running:
                run("stop", *running)
            run("run", "--rm", "--no-deps", "--name", container, "backup")
        finally:
            for signum in (signal.SIGTERM, signal.SIGINT):
                signal.signal(signum, signal.SIG_IGN)
            # 中断时先终止可能仍在读取数据的容器，再恢复同步写入。
            cleanup = subprocess.run(["docker", "container", "rm", "--force", container], capture_output=True)
            if cleanup.returncode and b"No such container" not in cleanup.stderr:
                raise RuntimeError("Cannot confirm backup container stopped; sync remains stopped")
            if running:
                run("start", *running)


if __name__ == "__main__":
    main()
