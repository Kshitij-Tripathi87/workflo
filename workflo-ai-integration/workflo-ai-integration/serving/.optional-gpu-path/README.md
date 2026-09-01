# Optional GPU path (vLLM multi-LoRA)

This is **not** the default. The default serving backend is llama.cpp
(`../docker-compose.llamacpp.yml`) — CPU-only, MIT licensed, $0 compute.

Keep this directory as a documented upgrade if inference volume ever
justifies GPU rental. `model_router.py`'s public interface
(`generate_for_flag`, `generate_report`) does not change either way, so
switching backends later is a compose + client-base-URL change, not a
rewrite of the adapter routing or validation gate.

Differences vs llama-server default:

| Concern | llama.cpp (default) | vLLM (this path) |
|---|---|---|
| Hardware | CPU | NVIDIA GPU |
| Adapter format | GGUF (needs PEFT→GGUF conversion) | PEFT/HuggingFace dirs |
| Adapter selection | All loaded at start (scale 0); per-request `lora` field | Runtime `load_lora_adapter` / `unload_lora_adapter` or `--lora-modules` |
| Port | 8080 | 8000 |
| License / cost | MIT / $0 | Apache-2.0 / GPU rental |

Do not enable this path inside the demo sandbox until the post-demo
`NetworkMode.INFERENCE_ONLY` work lands — see
`docs/workflo/sandbox_contract.md` "Not Claimed (Post-Demo)".
