import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import RedisError

from app.core import cache as cache_module
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import configure_engine
from app.main import app

MYSQL_BASE_DIR = Path(r"C:\Program Files\MySQL\MySQL Server 8.4")


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"

    cache_module._redis_client = None
    cache_module._memory_store.clear()
    settings.database_url = f"sqlite:///{db_path.resolve().as_posix()}"
    settings.redis_enabled = False
    settings.celery_task_always_eager = True
    settings.celery_task_eager_propagates = True
    settings.upload_dir = str(upload_dir)
    settings.export_dir = str(export_dir)
    settings.auto_create_tables = True

    configure_engine(settings.database_url)
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def client_with_redis(tmp_path: Path):
    db_path = tmp_path / "test_redis.db"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    redis_url = "redis://127.0.0.1:6379/15"
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    try:
        redis_client.ping()
    except RedisError as exc:
        pytest.skip(f"Redis not available for integration test: {exc}")
    redis_client.flushdb()

    cache_module._redis_client = None
    cache_module._memory_store.clear()
    settings.database_url = f"sqlite:///{db_path.resolve().as_posix()}"
    settings.redis_enabled = True
    settings.redis_url = redis_url
    settings.celery_task_always_eager = True
    settings.celery_task_eager_propagates = True
    settings.upload_dir = str(upload_dir)
    settings.export_dir = str(export_dir)
    settings.auto_create_tables = True

    configure_engine(settings.database_url)
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url=redis_url,
        result_backend=redis_url,
    )

    with TestClient(app) as test_client:
        yield test_client, redis_client

    redis_client.flushdb()


@pytest.fixture()
def client_with_mysql(tmp_path: Path):
    mysqld = MYSQL_BASE_DIR / "bin" / "mysqld.exe"
    mysql = MYSQL_BASE_DIR / "bin" / "mysql.exe"
    mysqladmin = MYSQL_BASE_DIR / "bin" / "mysqladmin.exe"
    if not mysqld.exists() or not mysql.exists() or not mysqladmin.exists():
        pytest.skip("MySQL server binaries are not available for integration test.")

    port = _find_free_port()
    data_dir = tmp_path / "mysql-data"
    defaults_file = tmp_path / "mysql-test.ini"
    database_url = f"mysql+pymysql://root@127.0.0.1:{port}/zcpt_test?charset=utf8mb4"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    subprocess.run(
        [
            str(mysqld),
            "--initialize-insecure",
            f"--basedir={MYSQL_BASE_DIR}",
            f"--datadir={data_dir}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    defaults_file.write_text(
        "\n".join(
            [
                "[mysqld]",
                f"basedir={MYSQL_BASE_DIR.as_posix()}",
                f"datadir={data_dir.as_posix()}",
                f"port={port}",
                "bind-address=127.0.0.1",
                "mysqlx=0",
                "",
            ]
        ),
        encoding="ascii",
    )

    proc = subprocess.Popen(
        [str(mysqld), f"--defaults-file={defaults_file}", "--console"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_mysql(mysqladmin, port, proc)

        subprocess.run(
            [
                str(mysql),
                "--protocol=TCP",
                "-h",
                "127.0.0.1",
                "-P",
                str(port),
                "-u",
                "root",
                "-e",
                "CREATE DATABASE IF NOT EXISTS zcpt_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
        )

        cache_module._redis_client = None
        cache_module._memory_store.clear()
        settings.database_url = database_url
        settings.redis_enabled = False
        settings.celery_task_always_eager = True
        settings.celery_task_eager_propagates = True
        settings.auto_create_tables = False
        settings.upload_dir = str(tmp_path / "uploads")
        settings.export_dir = str(tmp_path / "exports")
        configure_engine(settings.database_url)
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
            broker_url="memory://",
            result_backend="cache+memory://",
        )

        with TestClient(app) as test_client:
            yield test_client
    finally:
        subprocess.run(
            [
                str(mysqladmin),
                "--protocol=TCP",
                "-h",
                "127.0.0.1",
                "-P",
                str(port),
                "-u",
                "root",
                "shutdown",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_mysql(mysqladmin: Path, port: int, proc: subprocess.Popen[str]) -> None:
    for _ in range(60):
        result = subprocess.run(
            [
                str(mysqladmin),
                "--protocol=TCP",
                "-h",
                "127.0.0.1",
                "-P",
                str(port),
                "-u",
                "root",
                "ping",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        if proc.poll() is not None:
            stdout = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"MySQL process exited early: {stdout}")
        time.sleep(2)
    raise RuntimeError("MySQL temporary instance did not become ready in time.")
