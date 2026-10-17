"""Run real Lua against isolated Redis, never an existing Redis deployment.

Requires redis-server on PATH; skipped explicitly on platforms without it.
The subprocess uses only a temporary Unix socket and disables TCP/persistence.
"""

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
import redis

from services.service_auth import _NONCE_SCRIPT


@pytest.fixture
def isolated_redis(tmp_path):
    executable = shutil.which("redis-server")
    if sys.platform == "win32":
        pytest.skip("isolated Redis requires Unix sockets; exercised by Linux CI")
    if not executable:
        if os.environ.get("CI"):
            pytest.fail("Linux CI must provide redis-server for nonce security tests")
        pytest.skip("local optional test requires redis-server")
    socket = str(tmp_path / "nonce.sock")
    process = subprocess.Popen(
        [
            executable,
            "--port",
            "0",
            "--unixsocket",
            socket,
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    store = redis.Redis(unix_socket_path=socket, socket_timeout=1)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                if store.ping():
                    break
            except redis.RedisError:
                if time.monotonic() >= deadline:
                    pytest.fail("isolated Redis startup timeout")
                time.sleep(0.02)
        yield store, socket
    finally:
        store.close()
        process.terminate()
        process.wait(timeout=5)


def test_atomic_concurrent_nonce_claims(isolated_redis):
    store, _ = isolated_redis
    from concurrent.futures import ThreadPoolExecutor

    def claim(_):
        return store.eval(_NONCE_SCRIPT, 1, "peer", 100, "nonce", 701, 1000, 602)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(claim, range(20)))
    assert results.count(1) == 1
    assert results.count(0) == 19
    assert 0 < store.ttl("peer") <= 602


def test_future_timestamp_replay_and_quota(isolated_redis):
    store, _ = isolated_redis
    assert store.eval(_NONCE_SCRIPT, 1, "peer", 100, "a", 701, 2, 602) == 1
    # Timestamp + skew still valid even after receipt + skew has elapsed.
    assert store.eval(_NONCE_SCRIPT, 1, "peer", 401, "a", 701, 2, 602) == 0
    assert store.eval(_NONCE_SCRIPT, 1, "peer", 401, "b", 701, 2, 602) == 1
    assert store.eval(_NONCE_SCRIPT, 1, "peer", 401, "c", 701, 2, 602) == -1
    assert store.zcard("peer") == 2
    assert store.eval(_NONCE_SCRIPT, 1, "peer", 702, "c", 1002, 2, 602) == 1


def test_separate_processes_reject_same_nonce(isolated_redis):
    _, socket = isolated_redis
    backend = Path(__file__).resolve().parents[2] / "src/console/backend"
    code = """
import asyncio, sys
from config import settings
from services.service_auth import _consume_nonce
settings.integration_nonce_redis_url = 'unix://' + sys.argv[1]
print(asyncio.run(_consume_nonce('peer', 'a' * 32, 100, 701, 300)))
"""
    env = {**os.environ, "PYTHONPATH": str(backend)}
    results = [
        subprocess.run(
            [sys.executable, "-c", code, socket],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(2)
    ]
    assert results == ["1", "0"]


def test_async_client_calls_real_lua(isolated_redis, monkeypatch):
    _, socket = isolated_redis
    from config import settings
    from services.service_auth import _consume_nonce

    monkeypatch.setattr(settings, "integration_nonce_redis_url", "unix://" + socket)
    assert asyncio.run(_consume_nonce("async-peer", "b" * 32, 100, 701, 300)) == 1
    assert asyncio.run(_consume_nonce("async-peer", "b" * 32, 101, 701, 300)) == 0
