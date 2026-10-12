#!/usr/bin/env python3
"""QLoRA fine-tuning for the three Workflo task adapters.

IMPORTANT â€” training uses the ORIGINAL Hugging Face weights of the base
model (safetensors), NOT the serving GGUF. The GGUF is produced later by
scripts/convert_peft_to_gguf.py, which merges each trained LoRA against the
frozen serving GGUF.

The text format below mirrors model_router._build_prompt byte-for-byte:
    <|im_start|>system\n{system}<|im_end|>\n
    <|im_start|>user\n{user}<|im_end|>\n
    <|im_start|>assistant\n{assistant}<|im_end|>\n
Loss is computed on the completion only (response template masking), so the
adapters learn to emit the JSON payload and the <|im_end|> stop token.

Example:
    python train/train_qlora.py \
        --task test_gen \
        --dataset train/datasets/test_gen.jsonl \
        --base-model Qwen/Qwen3-4B \
        --output-dir train/out/test_gen \
        --epochs 3

GPU requirement: one >=16 GB VRAM GPU for a 4B base at rank 16 (QLoRA NF4).
CPU training is not practical; do not fake a run without a GPU.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RESPONSE_TEMPLATE = "<|im_start|>assistant\n"
DEFAULT_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def render_example(example: dict) -> str:
    return (
        f"<|im_start|>system\n{example['system']}<|im_end|>\n"
        f"<|im_start|>user\n{example['user']}<|im_end|>\n"
        f"<|im_start|>assistant\n{example['assistant']}<|im_end|>\n"
    )


def load_dataset(path: Path) -> list[dict]:
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        for field in ("system", "user", "assistant"):
            if not record.get(field):
                raise ValueError(f"{path}:{lineno}: empty '{field}'")
        records.append(record)
    if not records:
        raise ValueError(f"{path}: no examples")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=["test_gen", "reasoning", "reporting"])
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument(
        "--base-model",
        required=True,
        help="HF repo id or local directory with the ORIGINAL safetensors weights",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-len", type=int, default=4096)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument(
        "--gradient-checkpointing",
        action="store_true",
        help="trade compute for VRAM (required for small GPUs)",
    )
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    # Imported lazily so --help and dataset validation work without torch.
    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from trl import SFTConfig, SFTTrainer

    # Windows: trl's fused LM-head loss kernel is Triton-based (Linux-only);
    # on Windows trl.trainer.utils sets _ChunkedLogProbFunction = None but
    # sft_trainer still patches model.forward unconditionally, which crashes
    # on the first step ('NoneType' object has no attribute 'apply').
    # Inject a torch-native equivalent with the same call contract so the
    # fused forward works and gradients flow through standard ops.
    import trl.trainer.utils as _trl_utils

    if _trl_utils._ChunkedLogProbFunction is None:

        class _TorchChunkedLogProb:
            """torch-native ChunkedLogProbFunction (same contract, autograd via standard ops)."""

            TOKEN_CHUNK = 128

            @staticmethod
            def apply(
                hidden,
                weight,
                bias,
                targets,
                temperature,
                chunk_size,
                final_logit_softcapping=None,
                logit_scale=1.0,
                outputs=None,
            ):
                outputs = (
                    ("entropy", "log_sum_sq_probs", "mean_logits", "is_top1")
                    if outputs is None
                    else outputs
                )
                device = hidden.device
                n_tokens = hidden.shape[0]
                vocab = weight.shape[0]
                inv_t = 1.0 / temperature
                want = set(outputs)

                logprobs = torch.empty(n_tokens, device=device, dtype=torch.float32)
                entropy = (
                    torch.empty(n_tokens, device=device, dtype=torch.float32)
                    if "entropy" in want
                    else None
                )
                log_sum_sq = (
                    torch.empty(n_tokens, device=device, dtype=torch.float32)
                    if "log_sum_sq_probs" in want
                    else None
                )
                mean_logits = (
                    torch.empty(n_tokens, device=device, dtype=torch.float32)
                    if "mean_logits" in want
                    else None
                )
                is_top1 = (
                    torch.empty(n_tokens, device=device, dtype=torch.bool)
                    if "is_top1" in want
                    else None
                )

                for t0 in range(0, n_tokens, _TorchChunkedLogProb.TOKEN_CHUNK):
                    t1 = min(t0 + _TorchChunkedLogProb.TOKEN_CHUNK, n_tokens)
                    h = hidden[t0:t1]
                    tgt = targets[t0:t1]
                    n = t1 - t0
                    run_max = torch.full((n,), float("-inf"), device=device, dtype=torch.float32)
                    run_sum = torch.zeros((n,), device=device, dtype=torch.float32)
                    x_sum = torch.zeros((n,), device=device, dtype=torch.float32)
                    sq_sum = torch.zeros((n,), device=device, dtype=torch.float32)
                    z_sum = torch.zeros((n,), device=device, dtype=torch.float32)
                    amax_val = torch.full((n,), float("-inf"), device=device, dtype=torch.float32)
                    amax_idx = torch.zeros((n,), device=device, dtype=torch.long)
                    target_logit = torch.zeros((n,), device=device, dtype=torch.float32)

                    for v0 in range(0, vocab, chunk_size):
                        v1 = min(v0 + chunk_size, vocab)
                        # bf16 mm (weight stays bf16 - no full-weight fp32 copies);
                        # fp32 math on the [n, v] tile only.
                        tile = h @ weight[v0:v1].t()
                        if bias is not None:
                            tile = tile + bias[v0:v1]
                        z = tile.float() * logit_scale
                        if final_logit_softcapping is not None:
                            z = final_logit_softcapping * torch.tanh(
                                z / final_logit_softcapping
                            )
                        z = z * inv_t

                        sel = (tgt >= v0) & (tgt < v1)
                        if sel.any():
                            rows = sel.nonzero(as_tuple=True)[0]
                            target_logit[rows] = z[rows, tgt[rows] - v0]

                        cmax, cidx = z.max(dim=-1)
                        cidx = cidx + v0
                        better = cmax > run_max
                        first_tie = (cmax == run_max) & (cidx < amax_idx)
                        upd = better | first_tie
                        run_max = torch.where(upd, cmax, run_max)
                        amax_idx = torch.where(upd, cidx, amax_idx)

                        # logsumexp-based online merge (fewer saved tensors than
                        # a manual exp/sum; backward recomputes softmax from z)
                        chunk_lse = torch.logsumexp(z, dim=-1)
                        merged_max = torch.maximum(run_max, chunk_lse)
                        run_sum = (
                            run_sum * torch.exp(run_max - merged_max)
                            + torch.exp(chunk_lse - merged_max)
                        )
                        p = torch.exp(z - (chunk_lse.unsqueeze(-1)))
                        x_sum = x_sum + (p * z).sum(dim=-1)
                        sq_sum = sq_sum + (p * p).sum(dim=-1)
                        z_sum = z_sum + z.sum(dim=-1)
                        run_max = merged_max

                    log_z = run_max + torch.log(run_sum)
                    logprobs[t0:t1] = target_logit - log_z
                    if entropy is not None:
                        entropy[t0:t1] = log_z - x_sum / run_sum
                    if log_sum_sq is not None:
                        log_sum_sq[t0:t1] = torch.log(sq_sum) - 2.0 * torch.log(run_sum)
                    if mean_logits is not None:
                        mean_logits[t0:t1] = z_sum / vocab
                    if is_top1 is not None:
                        is_top1[t0:t1] = amax_idx == tgt

                return logprobs, entropy, log_sum_sq, mean_logits, is_top1

        _trl_utils._ChunkedLogProbFunction = _TorchChunkedLogProb
        print("trl fused-loss kernel unavailable (Windows) - injected torch-native chunked log-prob")

    records = load_dataset(args.dataset)
    print(f"loaded {len(records)} examples for task '{args.task}'")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    from transformers import AutoModelForImageTextToText

    try:
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            quantization_config=quant,
            device_map="auto",
            max_memory={0: "5.0GiB"},
            dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        )
    except (ValueError, KeyError, OSError) as exc:
        print(f"AutoModelForCausalLM failed ({exc}); trying image-text-to-text class")
        model = AutoModelForImageTextToText.from_pretrained(
            args.base_model,
            quantization_config=quant,
            device_map="auto",
            max_memory={0: "5.0GiB"},
            dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        )
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    lora = LoraConfig(
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=DEFAULT_TARGET_MODULES,
    )

    train_dataset = Dataset.from_list(
        [{**record, "text": render_example(record)} for record in records]
    )

    config = SFTConfig(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        logging_steps=5,
        save_strategy="epoch",
        bf16=True,
        max_length=args.max_seq_len,
        packing=False,
        completion_only_loss=True,
        gradient_checkpointing=args.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False}
        if args.gradient_checkpointing
        else None,
        seed=args.seed,
        report_to=[],
    )

    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=train_dataset,
        peft_config=lora,
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(str(args.output_dir / "final"))

    adapter_dir = args.output_dir / "final"
    for required in ("adapter_config.json",):
        if not (adapter_dir / required).is_file():
            raise RuntimeError(f"training finished but {required} missing in {adapter_dir}")
    print(f"adapter saved -> {adapter_dir}")
    print("next: python scripts/convert_peft_to_gguf.py --peft-dir "
          f"{adapter_dir} --hf-config-dir <original HF weights dir> "
          "--base-gguf <frozen serving gguf> "
          "--llamacpp-dir <llama.cpp checkout> --out serving/adapters/<task>.gguf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


