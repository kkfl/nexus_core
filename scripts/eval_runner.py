"""RAG Evaluation Harness — recall@k and pass/fail reporting.

Usage:
    python scripts/eval_runner.py [--dataset scripts/golden_set.yaml] [--api-url http://localhost:8000]

Requires a running nexus-api with ingested KB documents.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
import yaml


def load_dataset(path: str) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("queries", [])


def run_search(api_url: str, token: str, query: str, top_k: int = 10,
               namespaces: list[str] | None = None) -> list[dict]:
    """Call KB search and return results."""
    payload = {
        "query": query,
        "top_k": top_k,
        "namespaces": namespaces or ["global"],
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.post(f"{api_url}/kb/search", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def evaluate_query(results: list[dict], expected: dict, k: int = 5) -> dict:
    """Evaluate a single query against expected results."""
    result_doc_ids = [r["document_id"] for r in results[:k]]
    result_texts = " ".join(r["text"] for r in results[:k]).lower()

    # Check expected document IDs
    expected_doc_ids = expected.get("expected_doc_ids", [])
    found_docs = [str(d) for d in expected_doc_ids if str(d) in result_doc_ids]
    doc_recall = len(found_docs) / max(len(expected_doc_ids), 1)

    # Check expected keywords
    expected_keywords = expected.get("expected_keywords", [])
    found_keywords = [kw for kw in expected_keywords if kw.lower() in result_texts]
    keyword_recall = len(found_keywords) / max(len(expected_keywords), 1)

    # Reciprocal rank for first matching doc
    rr = 0.0
    for i, doc_id in enumerate(result_doc_ids):
        if str(doc_id) in [str(d) for d in expected_doc_ids]:
            rr = 1.0 / (i + 1)
            break

    passed = (doc_recall >= 0.5 or not expected_doc_ids) and \
             (keyword_recall >= 0.5 or not expected_keywords)

    return {
        "doc_recall_at_k": round(doc_recall, 3),
        "keyword_recall_at_k": round(keyword_recall, 3),
        "reciprocal_rank": round(rr, 3),
        "found_docs": found_docs,
        "found_keywords": found_keywords,
        "passed": passed,
    }


def main():
    parser = argparse.ArgumentParser(description="RAG Evaluation Harness")
    parser.add_argument("--dataset", default="scripts/golden_set.yaml",
                        help="Path to evaluation dataset (YAML)")
    parser.add_argument("--api-url", default="http://localhost:8000",
                        help="Nexus API base URL")
    parser.add_argument("--token", default="",
                        help="JWT token for API authentication")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of results to retrieve per query")
    parser.add_argument("--output", default="scripts/eval_report.json",
                        help="Output report file path")
    args = parser.parse_args()

    if not args.token:
        # Try to get a token via login
        print("No token provided, attempting admin login...")
        try:
            resp = httpx.post(f"{args.api_url}/auth/login", data={
                "username": "admin@nexus.local", "password": "admin_password"
            }, timeout=10)
            resp.raise_for_status()
            args.token = resp.json()["access_token"]
            print("  [OK] Login successful")
        except Exception as e:
            print(f"  [FAIL] Login failed: {e}")
            print("  Provide --token manually")
            sys.exit(1)

    dataset = load_dataset(args.dataset)
    if not dataset:
        print("No queries in dataset, nothing to evaluate.")
        sys.exit(0)

    print(f"\nRunning evaluation on {len(dataset)} queries (top_k={args.top_k})")
    print("=" * 60)

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "dataset": args.dataset,
        "top_k": args.top_k,
        "queries": [],
        "summary": {},
    }

    total_passed = 0
    total_doc_recall = 0.0
    total_keyword_recall = 0.0
    total_rr = 0.0

    for i, item in enumerate(dataset):
        query = item["question"]
        namespaces = item.get("namespaces", ["global"])
        print(f"\n  [{i+1}/{len(dataset)}] {query}")

        try:
            results = run_search(args.api_url, args.token, query, args.top_k, namespaces)
            eval_result = evaluate_query(results, item, args.top_k)

            status = "[PASS]" if eval_result["passed"] else "[FAIL]"
            print(f"    {status} | doc_recall={eval_result['doc_recall_at_k']}"
                  f" keyword_recall={eval_result['keyword_recall_at_k']}"
                  f" RR={eval_result['reciprocal_rank']}")

            report["queries"].append({
                "question": query,
                "results_count": len(results),
                **eval_result,
            })

            total_passed += int(eval_result["passed"])
            total_doc_recall += eval_result["doc_recall_at_k"]
            total_keyword_recall += eval_result["keyword_recall_at_k"]
            total_rr += eval_result["reciprocal_rank"]

        except Exception as e:
            print(f"    [ERROR]: {e}")
            report["queries"].append({
                "question": query,
                "error": str(e),
                "passed": False,
            })

    n = len(dataset)
    report["summary"] = {
        "total_queries": n,
        "passed": total_passed,
        "failed": n - total_passed,
        "pass_rate": round(total_passed / n, 3) if n else 0,
        "avg_doc_recall": round(total_doc_recall / n, 3) if n else 0,
        "avg_keyword_recall": round(total_keyword_recall / n, 3) if n else 0,
        "mrr": round(total_rr / n, 3) if n else 0,
    }

    print("\n" + "=" * 60)
    print(f"  SUMMARY: {total_passed}/{n} passed"
          f" | avg_doc_recall={report['summary']['avg_doc_recall']}"
          f" | MRR={report['summary']['mrr']}")
    print("=" * 60)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
