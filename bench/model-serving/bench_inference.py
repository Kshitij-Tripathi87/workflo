#!/usr/bin/env python3
"""Model-serving benchmark harness — throughput and unit economics.

Answers the two questions that decide whether the hosted edition's per-request
cost works: *how many requests per second does one serving instance sustain*,
and *what does a request cost at that rate*.

It drives any OpenAI-compatible ``/v1/chat/completions`` endpoint, so the same
command benchmarks the local vLLM deployment (``infra/vllm``) and the hosted
inference gateway.

    # local vLLM (infra/vllm/docker-compose.yml), the deployment target
    python bench/model-serving/bench_inference.py \
        --base-url http://localhost:8000 --model Qwen/Qwen2.5-Coder-7B-AWQ \
        --levels 1,2,4 --requests-per-level 32 \
        --out bench/results/vllm.json --md bench/results/vllm.md

Cost is an *assumption*, never a measurement: pass the real amortized rate for
the serving instance via ``--gpu-hourly-usd``. Every report records the value
used, and the JSON/Markdown output label the cost fields as estimates derived
from it, so a report can never be mistaken for measured spend.

Exit status: 0 all requests succeeded, 1 one or more requests failed (the
report is still written — a partial run is still evidence), 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The operator must supply the hourly cost assumption explicitly. There is no
# safe default: an invented rate would make estimated unit economics misleading.
DEFAULT_PATH = "/v1/chat/completions"
DEFAULT_PROMPT = (
    "Return exactly this JSON and nothing else: "
    '{"done": true, "steps": []}'
)


@dataclass
class RequestResult:
    """One request's outcome. `ok` is False for transport/HTTP errors."""

    latency_s: float
    ok: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


@dataclass
class LevelResult:
    """Aggregated metrics for one concurrency level."""

    concurrency: int
    requested: int
    succeeded: int = 0
    failed: int = 0
    wall_s: float = 0.0
    latencies_s: list[float] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: list[str] = field(default_factory=list)

    # ---- derived ----------------------------------------------------------
    @property
    def rps(self) -> float:
        """Completed requests per wall-clock second (0 when nothing completed)."""
        if self.wall_s <= 0:
            return 0.0
        return self.succeeded / self.wall_s

    def percentile_ms(self, pct: float) -> float:
        """Nearest-rank percentile of the successful latencies, in ms."""
        if not self.latencies_s:
            return 0.0
        ordered = sorted(self.latencies_s)
        rank = max(1, min(len(ordered), round(pct / 100.0 * len(ordered) + 0.5)))
        return ordered[rank - 1] * 1000.0

    @property
    def mean_ms(self) -> float:
        return statistics.fmean(self.latencies_s) * 1000.0 if self.latencies_s else 0.0

    @property
    def completion_tokens_per_s(self) -> float:
        """Decode throughput: aggregate completion tokens / wall seconds."""
        if self.wall_s <= 0:
            return 0.0
        return self.completion_tokens / self.wall_s

    def cost_per_request_usd(self, gpu_hourly_usd: float) -> float:
        """Estimated marginal cost of one request at this concurrency.

        A serving instance costs ``gpu_hourly_usd`` per hour whether it is idle
        or saturated, so the cost of a request is the cost of the wall time it
        occupies: ``gpu_hourly / (rps * 3600)``.
        """
        if self.rps <= 0:
            return 0.0
        return gpu_hourly_usd / (self.rps * 3600.0)

    def to_dict(self, gpu_hourly_usd: float) -> dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "requests": self.requested,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "wall_seconds": round(self.wall_s, 4),
            "rps": round(self.rps, 3),
            "latency_ms": {
                "p50": round(self.percentile_ms(50), 2),
                "p95": round(self.percentile_ms(95), 2),
                "mean": round(self.mean_ms, 2),
                "max": round(max(self.latencies_s) * 1000.0, 2) if self.latencies_s else 0.0,
            },
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "completion_tokens_per_second": round(self.completion_tokens_per_s, 2),
            "cost_per_request_usd": round(self.cost_per_request_usd(gpu_hourly_usd), 8),
            "errors": self.errors[:5],
        }


def build_payload(model: str, prompt: str, max_tokens: int) -> bytes:
    """OpenAI-compatible chat-completions body. temperature=0 keeps runs comparable."""
    return json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode("utf-8")


def one_request(
    url: str, payload: bytes, timeout_s: float, api_key: str | None
) -> RequestResult:
    """POST one completion and time it end-to-end (connection + full body read)."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf-8", "replace") if e.fp else ""
        return RequestResult(
            latency_s=time.perf_counter() - started,
            ok=False,
            error=f"HTTP {e.code}: {detail}",
        )
    except Exception as e:  # noqa: BLE001 - reported, never fatal
        return RequestResult(
            latency_s=time.perf_counter() - started,
            ok=False,
            error=f"{type(e).__name__}: {e}",
        )

    latency = time.perf_counter() - started
    usage = body.get("usage") or {}
    return RequestResult(
        latency_s=latency,
        ok=True,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


def run_level(
    url: str,
    payload: bytes,
    concurrency: int,
    requests_count: int,
    timeout_s: float,
    api_key: str | None,
    warmup: int,
) -> LevelResult:
    """Fire `requests_count` requests with `concurrency` workers; time the batch.

    Warmup requests run first and are excluded from every metric, so the first
    request's connection setup / model warmup cannot skew a low-concurrency
    level (which is exactly where it would hurt most).
    """
    for _ in range(max(0, warmup)):
        one_request(url, payload, timeout_s, api_key)

    result = LevelResult(concurrency=concurrency, requested=requests_count)
    if requests_count <= 0:
        return result

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        outcomes = list(
            pool.map(
                lambda _: one_request(url, payload, timeout_s, api_key),
                range(requests_count),
            )
        )
    result.wall_s = time.perf_counter() - started

    for outcome in outcomes:
        if outcome.ok:
            result.succeeded += 1
            result.latencies_s.append(outcome.latency_s)
            result.prompt_tokens += outcome.prompt_tokens
            result.completion_tokens += outcome.completion_tokens
        else:
            result.failed += 1
            if outcome.error:
                result.errors.append(outcome.error)

    return result


def parse_levels(raw: str) -> list[int]:
    """Parse ``--levels 1,4`` into ``[1, 4]`` (deduped, sorted, positive)."""
    levels: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        value = int(chunk)
        if value < 1:
            raise ValueError(f"concurrency levels must be >= 1, got {value}")
        if value not in levels:
            levels.append(value)
    if not levels:
        raise ValueError("no concurrency levels given")
    return sorted(levels)


def render_markdown(report: dict[str, Any]) -> str:
    """Human-readable report. Cost columns are labelled as estimates."""
    lines: list[str] = []
    lines.append("# Model-serving benchmark")
    lines.append("")
    lines.append(f"- **Mode:** {report['mode']}")
    lines.append(f"- **Endpoint:** {report['base_url']}{report['path']}")
    lines.append(f"- **Model:** {report['model']}")
    lines.append(f"- **Started:** {report['started_at']}")
    lines.append(f"- **Requests per level:** {report['requests_per_level']}")
    lines.append(f"- **Warmup requests per level:** {report['warmup']}")
    lines.append("")

    lines.append("## Throughput and latency")
    lines.append("")
    lines.append(
        "| concurrency | succeeded | failed | wall (s) | rps | p50 (ms) | p95 (ms) | "
        "max (ms) | completion tok/s |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for level in report["levels"]:
        latency = level["latency_ms"]
        lines.append(
            f"| {level['concurrency']} | {level['succeeded']} | {level['failed']} | "
            f"{level['wall_seconds']} | {level['rps']} | {latency['p50']} | "
            f"{latency['p95']} | {latency['max']} | {level['completion_tokens_per_second']} |"
        )
    lines.append("")

    assumptions = report["assumptions"]
    lines.append("## Estimated unit economics")
    lines.append("")
    lines.append(
        f"Derived from an **assumed** instance cost of "
        f"${assumptions['gpu_hourly_usd']:.2f}/hour — not a measured spend. "
        "Override with `--gpu-hourly-usd` using your real rate."
    )
    lines.append("")
    lines.append("| concurrency | est. cost/request (USD) | est. cost/1k requests (USD) |")
    lines.append("| --- | --- | --- |")
    for key in sorted(report["economics"], key=int):
        econ = report["economics"][key]
        cost = econ["cost_per_request_usd"]
        lines.append(f"| {key} | {cost:.8f} | {cost * 1000:.6f} |")
    lines.append("")

    failures = [
        (level["concurrency"], error)
        for level in report["levels"]
        for error in level["errors"]
    ]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for concurrency, error in failures:
            lines.append(f"- concurrency {concurrency}: {error}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by `bench/model-serving/bench_inference.py`. "
        "Latency is measured end-to-end from the client (new connection per "
        "request), so it includes network setup."
    )
    return "\n".join(lines) + "\n"


def run_benchmark(args: argparse.Namespace) -> int:
    """Execute every level, write both reports, return the process exit code."""
    url = args.base_url.rstrip("/") + args.path
    payload = build_payload(args.model, args.prompt, args.max_tokens)
    levels = parse_levels(args.levels)

    if not args.quiet:
        print(f"[bench] {args.mode} -> {url} (model={args.model})")

    results: list[LevelResult] = []
    for concurrency in levels:
        result = run_level(
            url=url,
            payload=payload,
            concurrency=concurrency,
            requests_count=args.requests_per_level,
            timeout_s=args.timeout,
            api_key=args.api_key,
            warmup=args.warmup,
        )
        results.append(result)
        if not args.quiet:
            print(
                f"[bench] concurrency={concurrency:<3} rps={result.rps:8.2f} "
                f"p50={result.percentile_ms(50):7.1f}ms p95={result.percentile_ms(95):7.1f}ms "
                f"ok={result.succeeded}/{result.requested}"
            )
            for error in result.errors[:2]:
                print(f"[bench]   ! {error}")

    report: dict[str, Any] = {
        "mode": args.mode,
        "base_url": args.base_url.rstrip("/"),
        "path": args.path,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "requests_per_level": args.requests_per_level,
        "warmup": args.warmup,
        "timeout_seconds": args.timeout,
        "started_at": args.started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "levels": [r.to_dict(args.gpu_hourly_usd) for r in results],
        "economics": {
            str(r.concurrency): {
                "rps": round(r.rps, 3),
                "cost_per_request_usd": round(r.cost_per_request_usd(args.gpu_hourly_usd), 8),
                "assumption_gpu_hourly_usd": args.gpu_hourly_usd,
            }
            for r in results
        },
        "assumptions": {
            "gpu_hourly_usd": args.gpu_hourly_usd,
            "note": (
                "Cost figures are ESTIMATES derived from this assumed hourly "
                "instance cost, not measured spend."
            ),
        },
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"[bench] wrote {out_path}")
    if args.md:
        md_path = Path(args.md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")
        if not args.quiet:
            print(f"[bench] wrote {md_path}")

    total_failed = sum(r.failed for r in results)
    if total_failed:
        if not args.quiet:
            print(f"[bench] FAILED: {total_failed} request(s) did not complete", file=sys.stderr)
        return 1
    if all(r.succeeded == 0 for r in results):
        if not args.quiet:
            print("[bench] FAILED: no request succeeded at any level", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_inference.py",
        description="Benchmark an OpenAI-compatible inference endpoint.",
    )
    # Only "direct" is implemented: point --base-url/--path at whatever serves
    # the model (vLLM locally, or the control-plane inference gateway). The
    # argument exists so additional topologies (sandbox-executed, multi-replica)
    # can be added without changing the invocation contract.
    parser.add_argument("--mode", default="direct", choices=["direct"])
    parser.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    parser.add_argument("--path", default=DEFAULT_PATH, help="completions path")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key", default=None, help="bearer token, if the endpoint needs one")
    parser.add_argument("--levels", default="1,4", help="concurrency levels, e.g. 1,4")
    parser.add_argument("--requests-per-level", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout", type=float, default=60.0, help="per-request timeout (s)")
    parser.add_argument("--warmup", type=int, default=1, help="excluded warmup requests per level")
    parser.add_argument(
        "--gpu-hourly-usd",
        type=float,
        required=True,
        help=(
            "required assumed amortized cost of the serving instance in USD/hour; "
            "all cost output is estimated from this explicit input"
        ),
    )
    parser.add_argument("--out", default=None, help="write the JSON report here")
    parser.add_argument("--md", default=None, help="write the Markdown report here")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Reads sys.argv when called with no arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.started_at = datetime.now(UTC).isoformat()

    if args.requests_per_level < 1:
        parser.error("--requests-per-level must be >= 1")
    if not math.isfinite(args.gpu_hourly_usd) or args.gpu_hourly_usd < 0:
        parser.error("--gpu-hourly-usd must be a finite number >= 0")
    try:
        parse_levels(args.levels)
    except ValueError as e:
        parser.error(str(e))

    try:
        return run_benchmark(args)
    except KeyboardInterrupt:
        print("[bench] interrupted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
