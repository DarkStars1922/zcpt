from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx

API_PREFIX = "/api/v1"


@dataclass
class Metrics:
    latencies: dict[str, list[float]] = field(default_factory=dict)
    statuses: dict[str, dict[int, int]] = field(default_factory=dict)
    errors: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, elapsed_ms: float, status_code: int) -> None:
        self.latencies.setdefault(name, []).append(elapsed_ms)
        bucket = self.statuses.setdefault(name, {})
        bucket[status_code] = bucket.get(status_code, 0) + 1

    def error(self, name: str) -> None:
        self.errors[name] = self.errors.get(name, 0) + 1

    def merge(self, other: "Metrics") -> None:
        for name, values in other.latencies.items():
            self.latencies.setdefault(name, []).extend(values)
        for name, statuses in other.statuses.items():
            target = self.statuses.setdefault(name, {})
            for status_code, count in statuses.items():
                target[status_code] = target.get(status_code, 0) + count
        for name, count in other.errors.items():
            self.errors[name] = self.errors.get(name, 0) + count


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q)))
    return ordered[index]


def summarize(metrics: Metrics, elapsed_seconds: float) -> dict[str, Any]:
    total_requests = sum(len(values) for values in metrics.latencies.values())
    result = {
        "elapsed_seconds": round(elapsed_seconds, 4),
        "total_requests": total_requests,
        "requests_per_second": round(total_requests / elapsed_seconds, 4) if elapsed_seconds else 0.0,
        "scenarios": {},
        "errors": metrics.errors,
    }
    for name, values in sorted(metrics.latencies.items()):
        result["scenarios"][name] = {
            "count": len(values),
            "rps": round(len(values) / elapsed_seconds, 4) if elapsed_seconds else 0.0,
            "avg_ms": round(statistics.mean(values), 4) if values else 0.0,
            "p50_ms": round(percentile(values, 0.50), 4),
            "p90_ms": round(percentile(values, 0.90), 4),
            "p95_ms": round(percentile(values, 0.95), 4),
            "p99_ms": round(percentile(values, 0.99), 4),
            "max_ms": round(max(values), 4) if values else 0.0,
            "statuses": metrics.statuses.get(name, {}),
            "errors": metrics.errors.get(name, 0),
        }
    return result


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def timed_request(metrics: Metrics, name: str, client: httpx.AsyncClient, method: str, url: str, **kwargs):
    started = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics.add(name, elapsed_ms, response.status_code)
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics.add(name, elapsed_ms, 0)
        metrics.error(name)
        return None


async def login(client: httpx.AsyncClient, account: str, password: str) -> str:
    response = await client.post(
        f"{API_PREFIX}/auth/login",
        json={"account": account, "password": password},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"login failed for {account}: {payload}")
    return payload["data"]["access_token"]


async def register_user(client: httpx.AsyncClient, account: str, password: str, class_id: int) -> None:
    response = await client.post(
        f"{API_PREFIX}/auth/register",
        json={
            "account": account,
            "password": password,
            "name": f"压测学生{account[-4:]}",
            "role": "student",
            "class_id": class_id,
            "email": f"{account}@example.com",
            "is_reviewer": False,
        },
    )
    if response.status_code != 200:
        return
    payload = response.json()
    if payload.get("code") not in {0, 1000}:
        return


async def prepare_tokens(args) -> list[str]:
    accounts = [item.strip() for item in args.accounts.split(",") if item.strip()]
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as client:
        if args.register_users > 0:
            tasks = [
                register_user(client, f"{args.register_prefix}{index:04d}", args.password, args.class_id)
                for index in range(args.register_users)
            ]
            for start in range(0, len(tasks), 50):
                await asyncio.gather(*tasks[start : start + 50])
        generated_users = max(args.register_users, args.generated_users)
        if generated_users > 0:
            accounts.extend(f"{args.register_prefix}{index:04d}" for index in range(generated_users))

        async def login_or_none(account: str) -> str | None:
            try:
                return await login(client, account, args.password)
            except Exception as exc:
                print(f"[warn] login skipped: {account}: {exc}")
                return None

        tokens = []
        for start in range(0, len(accounts), args.login_batch_size):
            batch = accounts[start : start + args.login_batch_size]
            results = await asyncio.gather(*(login_or_none(account) for account in batch))
            tokens.extend(token for token in results if token)
        if not tokens:
            raise RuntimeError("no login tokens available")
        return tokens


def build_upload_bytes(size_kb: int) -> bytes:
    size = max(1, size_kb) * 1024
    header = b"%PDF-1.4\n% load-test\n"
    return header + b"0" * max(0, size - len(header))


async def scenario_read(client: httpx.AsyncClient, metrics: Metrics, token: str) -> None:
    headers = auth_headers(token)
    await timed_request(metrics, "GET /applications/categories", client, "GET", f"{API_PREFIX}/applications/categories", headers=headers)
    await timed_request(metrics, "GET /applications/my/category-summary", client, "GET", f"{API_PREFIX}/applications/my/category-summary", headers=headers)
    await timed_request(
        metrics,
        "GET /applications/my/by-category",
        client,
        "GET",
        f"{API_PREFIX}/applications/my/by-category",
        headers=headers,
        params={"category": "innovation", "sub_type": "achievement", "page": 1, "size": 10},
    )
    await timed_request(metrics, "GET /announcements", client, "GET", f"{API_PREFIX}/announcements", headers=headers)


async def scenario_upload_and_submit(client: httpx.AsyncClient, metrics: Metrics, token: str, upload_bytes: bytes) -> None:
    headers = auth_headers(token)
    files = {"file": (f"load_{random.randint(1, 999999)}.pdf", upload_bytes, "application/pdf")}
    response = await timed_request(metrics, "POST /files/upload", client, "POST", f"{API_PREFIX}/files/upload", headers=headers, files=files)
    file_id = None
    if response is not None and response.status_code == 200:
        payload = response.json()
        if payload.get("code") == 0:
            file_id = payload.get("data", {}).get("file_id")
    if not file_id:
        return
    await timed_request(
        metrics,
        "POST /applications",
        client,
        "POST",
        f"{API_PREFIX}/applications",
        headers=headers,
        json={
            "award_uid": 316,
            "title": f"压测申报 {random.randint(1, 999999)}",
            "description": "load test application",
            "occurred_at": date.today().isoformat(),
            "attachments": [{"file_id": file_id}],
            "category": "innovation",
            "sub_type": "achievement",
            "score": 0,
        },
    )


async def worker(args, tokens: list[str], upload_bytes: bytes, semaphore: asyncio.Semaphore) -> Metrics:
    metrics = Metrics()
    limits = httpx.Limits(max_keepalive_connections=args.concurrency, max_connections=args.concurrency * 2)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout, limits=limits) as client:
        for _ in range(args.iterations):
            token = random.choice(tokens)
            async with semaphore:
                if args.mode in {"read", "mixed"}:
                    await scenario_read(client, metrics, token)
                if args.mode in {"write", "mixed"}:
                    await scenario_upload_and_submit(client, metrics, token, upload_bytes)
    return metrics


async def run(args) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as client:
        response = await client.get("/health")
        response.raise_for_status()
    tokens = await prepare_tokens(args)
    upload_bytes = build_upload_bytes(args.upload_kb)
    semaphore = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()
    tasks = [worker(args, tokens, upload_bytes, semaphore) for _ in range(args.clients)]
    worker_metrics = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - started
    metrics = Metrics()
    for item in worker_metrics:
        metrics.merge(item)
    summary = summarize(metrics, elapsed)
    summary["config"] = {
        "base_url": args.base_url,
        "mode": args.mode,
        "clients": args.clients,
        "concurrency": args.concurrency,
        "iterations_per_client": args.iterations,
        "tokens": len(tokens),
        "upload_kb": args.upload_kb,
    }
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="Simple async HTTP load test for the evaluation platform.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--accounts", default="student_normal,student_reviewer,student_302,student_reviewer_302")
    parser.add_argument("--password", default="pass1234")
    parser.add_argument("--register-users", type=int, default=0)
    parser.add_argument("--generated-users", type=int, default=0)
    parser.add_argument("--register-prefix", default="load_student_")
    parser.add_argument("--login-batch-size", type=int, default=100)
    parser.add_argument("--class-id", type=int, default=301)
    parser.add_argument("--mode", choices=["read", "write", "mixed"], default="mixed")
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--upload-kb", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json-output", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = asyncio.run(run(args))
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json_output:
        Path(args.json_output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
