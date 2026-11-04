"""Run a tenant-specific chat evaluation set against a deployed API.

Dataset format: one JSON object per line with college, question,
expected_contains (list), and forbidden_contains (optional list). Use only
verified answers from the institution; this tool does not generate fixtures.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * value))] if ordered else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate evidence-backed answers for real college tenants")
    parser.add_argument("dataset", type=Path, help="JSONL evaluation file using verified institutional answers")
    parser.add_argument("--api", default=os.getenv("CHAT_API", "http://localhost:8000/api/v1"))
    parser.add_argument("--allow-small", action="store_true", help="Allow fewer than 100 questions per college for a smoke run")
    parser.add_argument("--output", type=Path, default=Path("chat-eval-report.json"))
    args = parser.parse_args()
    email = os.getenv("CHAT_EVAL_EMAIL")
    password = os.getenv("CHAT_EVAL_PASSWORD")
    if not email or not password:
        parser.error("Set CHAT_EVAL_EMAIL and CHAT_EVAL_PASSWORD in the environment")

    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts: dict[str, int] = {}
    for row in rows:
        if not row.get("college") or not row.get("question") or not isinstance(row.get("expected_contains"), list):
            parser.error("Every line needs college, question, and expected_contains (list)")
        counts[row["college"]] = counts.get(row["college"], 0) + 1
    if not args.allow_small and (not counts or any(count < 100 for count in counts.values())):
        parser.error("Provide at least 100 verified questions for each college, or use --allow-small for a smoke run")

    outcomes = []
    latencies = []
    with httpx.Client(base_url=args.api.rstrip("/") + "/", timeout=45) as client:
        login = client.post("auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        for row in rows:
            conversation = client.post("conversations")
            conversation.raise_for_status()
            cid = conversation.json()["id"]
            connect = client.post("chat", json={"conversation_id": cid, "message": row["college"], "college": row["college"], "language": "en-IN"})
            connect.raise_for_status()
            start = time.perf_counter()
            response = client.post("chat", json={"conversation_id": cid, "message": row["question"], "language": "en-IN"})
            response.raise_for_status()
            elapsed = time.perf_counter() - start
            result = response.json()["message"]
            answer = str(result.get("content", ""))
            folded = answer.casefold()
            missing = [term for term in row["expected_contains"] if str(term).casefold() not in folded]
            forbidden = [term for term in row.get("forbidden_contains", []) if str(term).casefold() in folded]
            outcomes.append({"college": row["college"], "question": row["question"], "passed": not missing and not forbidden, "missing_expected": missing, "forbidden_present": forbidden, "source_badge": result.get("source_badge"), "sources": len(result.get("sources") or []), "response_seconds": round(elapsed, 3)})
            latencies.append(elapsed)
            print(f"{'PASS' if outcomes[-1]['passed'] else 'FAIL'} [{row['college']}] {row['question']}")

    report = {"total": len(outcomes), "passed": sum(row["passed"] for row in outcomes), "accuracy": sum(row["passed"] for row in outcomes) / max(1, len(outcomes)), "p95_seconds": round(percentile(latencies, .95), 3), "mean_seconds": round(statistics.mean(latencies), 3) if latencies else 0, "by_college": counts, "results": outcomes}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "passed", "accuracy", "p95_seconds", "mean_seconds", "by_college")}, ensure_ascii=False))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
