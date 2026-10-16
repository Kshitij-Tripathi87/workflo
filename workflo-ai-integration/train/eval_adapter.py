#!/usr/bin/env python3
"""Held-out evaluation for a trained adapter against the acceptance gate.

Gate (train/RETRAIN_PLAN.md section 5):
  1. completion token accuracy >= 0.84  (teacher-forced, held-out examples)
  2. schema-validity rate == 100 %      (greedy generation parsed + validated)
  3. safety-gate pass rate == 100 %     (compile_check / property_expr_check)

Uses the ORIGINAL HF weights + the trained LoRA adapter, exactly like
training, so the numbers reflect the adapter that will be converted.

Usage:
    python train/eval_adapter.py \
        --task reasoning \
        --adapter-dir train/out/reasoning_r32/final \
        --base-model ermiaazarkhalili/Qwen3.8-4B-SFT-Fable5-Glint \
        --eval-dataset train/datasets/splits/reasoning_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from workflo_ai_integration.safety_gate import (  # noqa: E402
    compile_check,
    property_expr_check,
)
from workflo_ai_integration.schemas import (  # noqa: E402
    ProposeInvariantCall,
    ReportNarrative,
    WriteTestCall,
)

SCHEMA_BY_TASK = {
    "test_gen": (WriteTestCall, "content"),
    "reasoning": (ProposeInvariantCall, None),
    "reporting": (ReportNarrative, None),
}

RESPONSE_TEMPLATE = "<|im_start|>assistant\n"


def load_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=list(SCHEMA_BY_TASK))
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--eval-dataset", required=True, type=Path)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    records = load_records(args.eval_dataset)
    schema_cls, gate_field = SCHEMA_BY_TASK[args.task]

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=quant,
        device_map="auto",
        max_memory={0: "5.0GiB"},
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(model, str(args.adapter_dir))
    model.eval()

    # -- 1. teacher-forced completion token accuracy -------------------------
    # Tokenize prompt+completion JOINTLY (matching the training collator);
    # separate tokenization would mis-split BPE merges across the
    # 'assistant\n{' boundary and measure the wrong targets.
    template_ids = tokenizer(
        RESPONSE_TEMPLATE, add_special_tokens=False
    ).input_ids

    def completion_boundary(full_ids: list[int]) -> int:
        """Last index where RESPONSE_TEMPLATE ends inside full_ids."""
        n = len(template_ids)
        for i in range(len(full_ids) - n, -1, -1):
            if full_ids[i : i + n] == template_ids:
                return i + n
        raise ValueError("response template not found in joint tokenization")

    correct = 0
    total = 0
    with torch.no_grad():
        for record in records:
            text = (
                f"<|im_start|>system\n{record['system']}<|im_end|>\n"
                f"<|im_start|>user\n{record['user']}<|im_end|>\n"
                f"<|im_start|>assistant\n{record['assistant']}<|im_end|>"
            )
            full_ids = tokenizer(text, add_special_tokens=False).input_ids
            start = completion_boundary(full_ids)
            input_ids = torch.tensor([full_ids], device=model.device)
            logits = model(input_ids=input_ids).logits
            predictions = logits[0, start - 1 : -1].argmax(dim=-1)
            targets = input_ids[0, start:]
            matches = predictions == targets
            correct += int(matches.sum())
            total += int(matches.numel())
    token_accuracy = correct / total if total else 0.0

    # -- 2 + 3. greedy generation: schema validity + safety gates -------------
    schema_valid = 0
    gate_pass = 0
    failures: list[str] = []
    with torch.no_grad():
        for record in records:
            prompt = (
                f"<|im_start|>system\n{record['system']}<|im_end|>\n"
                f"<|im_start|>user\n{record['user']}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            ids = tokenizer(prompt, return_tensors="pt").to(model.device)
            out = model.generate(
                **ids,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
            text = tokenizer.decode(out[0, ids.input_ids.shape[1]:], skip_special_tokens=True)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                failures.append("generation is not valid JSON")
                continue
            try:
                obj = schema_cls.model_validate(payload)
            except Exception:
                failures.append("schema validation failed")
                continue
            schema_valid += 1
            gate_ok = True
            if args.task == "test_gen":
                gate_ok = compile_check(obj.content).ok
            elif args.task == "reasoning":
                gate_ok = all(
                    property_expr_check(expr).ok
                    for expr in (obj.hypothesis_strategy, obj.property_check)
                )
            if gate_ok:
                gate_pass += 1
            else:
                failures.append("safety gate rejected generation")

    result = {
        "task": args.task,
        "adapter_dir": str(args.adapter_dir),
        "eval_examples": len(records),
        "completion_token_accuracy": round(token_accuracy, 4),
        "schema_valid_rate": round(schema_valid / len(records), 4) if records else 0.0,
        "gate_pass_rate": round(gate_pass / len(records), 4) if records else 0.0,
        "gate": {
            "token_accuracy_ge_0_84": token_accuracy >= 0.84,
            "schema_valid_100pct": schema_valid == len(records),
            "gate_pass_100pct": gate_pass == len(records),
        },
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    all_pass = all(result["gate"].values())
    print(f"ACCEPTANCE GATE: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
