#!/usr/bin/env python3
"""Model-serving benchmark harness — throughput and unit economics.

Answers the two questions that decide whether the hosted edition's per-request
cost works: *how many requests per second does one serving instance sustain*,
and *what does a request cost at that rate*.

It drives any OpenAI-compatible ``/v1/chat/completions`` endpoint, including
the selected CPU-first llama.cpp/GGUF path and the hosted inference gateway.
The optional vLLM manifest is a separate GPU experiment, not the release default.

    # llama.cpp server with a local GGUF model
    python bench/model-serving/bench_inference.py \
        --base-url http://localhost:8080 --model <served-model-id> \
        --instance-hourly-usd <measured-or-amortized-host-rate> \
        --levels 1,2,4 --requests-per-level 32 \
        --out bench/results/llama-cpp.json --md bench/results/llama-cpp.md

Cost is an *assumption*, never a measurement: pass the real amortized rate for
the serving instance via ``--instance-hourly-usd``. Every report records the value
used, and the JSON/Markdown output label the cost fields as estimates derived
from it, so a report can never be mistaken for measured spend.

Exit status: 0 all requests succeeded, 1 one or more requests failed (the
report is still written — a partial run is still evidence), 2 bad usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
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
    """One request's redacted outcome.

    Response content and canary values are inspected in memory and deliberately
    discarded. Only counts, timings, and classified outcomes reach evidence.
    """

    latency_s: float
    ok: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    canary_verified: bool = False
    leakage_detected: bool = False
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
    canaries_verified: int = 0
    leakage_failures: int = 0
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

    def cost_per_request_usd(self, instance_hourly_usd: float) -> float:
        """Estimated marginal cost of one request at this concurrency.

        A serving instance costs ``instance_hourly_usd`` per hour whether it is idle
        or saturated, so the cost of a request is the cost of the wall time it
        occupies: ``instance_hourly / (rps * 3600)``.
        """
        if self.rps <= 0:
            return 0.0
        return instance_hourly_usd / (self.rps * 3600.0)

    def to_dict(self, instance_hourly_usd: float) -> dict[str, Any]:
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
            "canaries_verified": self.canaries_verified,
            "leakage_failures": self.leakage_failures,
            "cost_per_request_usd": round(self.cost_per_request_usd(instance_hourly_usd), 8),
            "errors": self.errors[:5],
        }


def build_payload(
    model: str,
    prompt: str,
    max_tokens: int,
    canary: str | None = None,
) -> bytes:
    """Build one OpenAI request, optionally carrying an isolation canary."""
    request_prompt = prompt
    if canary:
        request_prompt = (
            f"{prompt}\nRequest isolation marker: {canary}\n"
            "Include that exact marker once in the response. Do not include any "
            "marker from another request."
        )
    return json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": request_prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode("utf-8")


def one_request(
    url: str,
    payload: bytes,
    timeout_s: float,
    api_key: str | None,
    expected_canary: str | None = None,
    foreign_canaries: tuple[str, ...] = (),
) -> RequestResult:
    """POST one completion and validate its per-request isolation marker."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Never retain an upstream response body: it can contain prompts,
        # credentials, or generated text. The status class is sufficient.
        return RequestResult(
            latency_s=time.perf_counter() - started,
            ok=False,
            error=f"http_status_{exc.code}",
        )
    except Exception as exc:  # noqa: BLE001 - classified, never fatal
        # Exception messages can contain credential-bearing URLs. Keep only
        # the exception identity in reports.
        return RequestResult(
            latency_s=time.perf_counter() - started,
            ok=False,
            error=f"transport_{type(exc).__name__}",
        )

    latency = time.perf_counter() - started
    if not isinstance(body, dict):
        return RequestResult(
            latency_s=latency,
            ok=False,
            error="invalid OpenAI response: JSON root must be an object",
        )

    choices = body.get("choices")
    if (
        not isinstance(choices, list)
        or not choices
        or not isinstance(choices[0], dict)
        or not isinstance(choices[0].get("message"), dict)
    ):
        return RequestResult(
            latency_s=latency,
            ok=False,
            error="invalid OpenAI response: expected non-empty choices with a message",
        )

    content = choices[0]["message"].get("content")
    if not isinstance(content, str):
        return RequestResult(
            latency_s=latency,
            ok=False,
            error="invalid_openai_message_content",
        )

    if expected_canary:
        foreign_leak = any(marker in content for marker in foreign_canaries)
        own_marker_present = expected_canary in content
        if foreign_leak:
            return RequestResult(
                latency_s=latency,
                ok=False,
                leakage_detected=True,
                error="cross_request_leakage",
            )
        if not own_marker_present:
            return RequestResult(
                latency_s=latency,
                ok=False,
                error="isolation_marker_missing",
            )

    usage = body.get("usage")
    if not isinstance(usage, dict) or not {
        "prompt_tokens",
        "completion_tokens",
    }.issubset(usage):
        return RequestResult(
            latency_s=latency,
            ok=False,
            error="invalid OpenAI response: usage.prompt_tokens and usage.completion_tokens are required",
        )
    try:
        prompt_tokens = int(usage["prompt_tokens"])
        completion_tokens = int(usage["completion_tokens"])
    except (TypeError, ValueError):
        return RequestResult(
            latency_s=latency,
            ok=False,
            error="invalid OpenAI response: token usage fields must be integers",
        )
    if prompt_tokens < 0 or completion_tokens < 0:
        return RequestResult(
            latency_s=latency,
            ok=False,
            error="invalid OpenAI response: token usage fields must be non-negative",
        )

    return RequestResult(
        latency_s=latency,
        ok=True,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        canary_verified=bool(expected_canary),
    )


def run_level(
    url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    concurrency: int,
    requests_count: int,
    timeout_s: float,
    api_key: str | None,
    warmup: int,
) -> LevelResult:
    """Run one level with a unique, response-validated marker per request.

    Canary values and response bodies never leave memory. Each response must
    contain its own marker and no marker assigned to another concurrent request.
    """
    for _ in range(max(0, warmup)):
        marker = f"WFISO-{secrets.token_hex(16)}"
        one_request(
            url,
            build_payload(model, prompt, max_tokens, marker),
            timeout_s,
            api_key,
            marker,
        )

    result = LevelResult(concurrency=concurrency, requested=requests_count)
    if requests_count <= 0:
        return result

    canaries = tuple(f"WFISO-{secrets.token_hex(16)}" for _ in range(requests_count))

    def send(index: int) -> RequestResult:
        own = canaries[index]
        foreign = canaries[:index] + canaries[index + 1 :]
        return one_request(
            url,
            build_payload(model, prompt, max_tokens, own),
            timeout_s,
            api_key,
            own,
            foreign,
        )

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        outcomes = list(pool.map(send, range(requests_count)))
    result.wall_s = time.perf_counter() - started

    for outcome in outcomes:
        if outcome.ok:
            result.succeeded += 1
            result.latencies_s.append(outcome.latency_s)
            result.prompt_tokens += outcome.prompt_tokens
            result.completion_tokens += outcome.completion_tokens
            result.canaries_verified += int(outcome.canary_verified)
        else:
            result.failed += 1
            result.leakage_failures += int(outcome.leakage_detected)
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
    lines.append(f"- **Endpoint SHA-256:** `{report['endpoint_sha256']}`")
    lines.append(f"- **Model:** {report['model']}")
    lines.append(f"- **Started:** {report['started_at']}")
    lines.append(f"- **Requests per level:** {report['requests_per_level']}")
    lines.append(f"- **Warmup requests per level:** {report['warmup']}")
    lines.append("")

    lines.append("## Throughput and latency")
    lines.append("")
    lines.append(
        "| concurrency | succeeded | failed | canaries | leaks | wall (s) | rps | "
        "p50 (ms) | p95 (ms) | max (ms) | completion tok/s |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for level in report["levels"]:
        latency = level["latency_ms"]
        lines.append(
            f"| {level['concurrency']} | {level['succeeded']} | {level['failed']} | "
            f"{level['canaries_verified']} | {level['leakage_failures']} | "
            f"{level['wall_seconds']} | {level['rps']} | {latency['p50']} | "
            f"{latency['p95']} | {latency['max']} | {level['completion_tokens_per_second']} |"
        )
    lines.append("")

    assumptions = report["assumptions"]
    lines.append("## Estimated unit economics")
    lines.append("")
    lines.append(
        f"Derived from an **assumed** instance cost of "
        f"${assumptions['instance_hourly_usd']:.2f}/hour — not a measured spend. "
        "Override with `--instance-hourly-usd` using your real rate."
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
    endpoint_sha256 = hashlib.sha256(url.encode("utf-8")).hexdigest()
    levels = parse_levels(args.levels)

    if not args.quiet:
        print(
            f"[bench] {args.mode} endpoint_sha256={endpoint_sha256} "
            f"(model={args.model})"
        )

    results: list[LevelResult] = []
    for concurrency in levels:
        result = run_level(
            url=url,
            model=args.model,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
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
        "endpoint_sha256": endpoint_sha256,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "requests_per_level": args.requests_per_level,
        "warmup": args.warmup,
        "timeout_seconds": args.timeout,
        "started_at": args.started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "levels": [r.to_dict(args.instance_hourly_usd) for r in results],
        "economics": {
            str(r.concurrency): {
                "rps": round(r.rps, 3),
                "cost_per_request_usd": round(r.cost_per_request_usd(args.instance_hourly_usd), 8),
                "assumption_instance_hourly_usd": args.instance_hourly_usd,
            }
            for r in results
        },
        "assumptions": {
            "instance_hourly_usd": args.instance_hourly_usd,
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
    parser.add_argument(
        "--api-key",
        default=os.environ.get("WORKFLO_MODEL_API_KEY"),
        help="bearer token, if the endpoint needs one (or WORKFLO_MODEL_API_KEY env var)",
    )
    parser.add_argument("--levels", default="1,4", help="concurrency levels, e.g. 1,4")
    parser.add_argument("--requests-per-level", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout", type=float, default=60.0, help="per-request timeout (s)")
    parser.add_argument("--warmup", type=int, default=1, help="excluded warmup requests per level")
    parser.add_argument(
        "--instance-hourly-usd", "--gpu-hourly-usd",
        dest="instance_hourly_usd",
        type=float,
        required=True,
        help=(
            "required assumed amortized cost of the serving instance (CPU or GPU) "
            "in USD/hour; all cost output is estimated from this explicit input"
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
    if not math.isfinite(args.instance_hourly_usd) or args.instance_hourly_usd < 0:
        parser.error("--instance-hourly-usd must be a finite number >= 0")
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
