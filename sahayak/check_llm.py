"""Check that the configured LLM is reachable AND supports tool calling.

    python -m sahayak.check_llm
    python -m sahayak.check_llm --model nvidia/nemotron-3-super-120b-a12b

Tool calling is essential for the agent; not every hosted model supports it.
"""
from __future__ import annotations

import argparse
import sys
import time

from .agent import make_client, resolve_config
from .llm_options import model_extra_body
from .tools import TOOL_SCHEMAS

# Models on NVIDIA's API that are worth trying if the default fails (check build.nvidia.com for current ones)
NVIDIA_FALLBACKS = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-nano-30b-a3b"]  # verify names on build.nvidia.com


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    args = ap.parse_args()

    base_url, api_key, model = resolve_config()
    model = args.model or model
    if api_key == "missing":
        print("No API key found. Run  . .\\scripts\\use_nvidia.ps1  or set LLM_* variables.")
        return 1
    print(f"Endpoint: {base_url or 'OpenAI default'}\nModel:    {model}")

    client = make_client()
    t0 = time.time()
    try:
        extra = model_extra_body(model)
        resp = client.chat.completions.create(
            model=model, temperature=0, tools=TOOL_SCHEMAS, **({"extra_body": extra} if extra else {}),
            messages=[{"role": "system", "content": "Use the tools to answer."},
                      {"role": "user", "content": "Check eligibility for a 75 year old."}])
    except Exception as e:
        print(f"\nFAILED: {type(e).__name__}: {e}")
        if getattr(e, "status_code", None) in (404, 410):
            print("NVIDIA refused this model for your key (HTTP 404/410): the name may be wrong, the model unavailable to your")
            print("account, or no longer hosted. Check it on build.nvidia.com, or use a model that works for you,")
            print("e.g. nvidia/nemotron-3-super-120b-a12b or nvidia/nemotron-3-nano-30b-a3b (check the exact names there).")
        if "nvidia" in (base_url or ""):
            print("Try another model, e.g.:  python -m sahayak.check_llm --model " + NVIDIA_FALLBACKS[0])
        return 1

    msg = resp.choices[0].message
    print(f"Reached the model in {time.time() - t0:.1f}s")
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        print(f"Tool calling works: {tc.function.name}({tc.function.arguments})")
        print("\nReady. Next:  python -m evals.run_agent_evals")
        return 0
    print("The model answered WITHOUT calling a tool, so it may not support tool calling here:")
    print("  " + (msg.content or "")[:300].replace("\n", " "))
    print("Try:  python -m sahayak.check_llm --model " + NVIDIA_FALLBACKS[0])
    return 2


if __name__ == "__main__":
    sys.exit(main())
