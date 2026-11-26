"""Manual smoke test against the real Gemini API (not run in CI). Synthetic input only.

ENVIRONMENT=development .venv/bin/python scripts/llm_smoke.py [--pro]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, Field  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.llm.base import CallMeta, ModelTier  # noqa: E402
from app.llm.gemini import GeminiClient  # noqa: E402
from app.llm.usage import InMemoryUsageStore, MeteredLLM, estimate_cost  # noqa: E402

PROMPT = (
    "Synthetic job advert (test data): 'Housemaid wanted in Kuwait. Salary 60 KWD per month. "
    "Pay a processing fee of LKR 350,000 to our agent before departure.' "
    "List the warning signs a migrant worker should check. Do not judge whether any agency is "
    "legal or safe."
)


class SmokeResult(BaseModel):
    warning_signs: list[str] = Field(max_length=5)
    risk: Literal["low", "medium", "high"]


async def main(tier: ModelTier) -> int:
    provider = GeminiClient()
    llm = MeteredLLM(provider, InMemoryUsageStore(), budget=50_000)
    try:
        result, usage = await llm.generate_json(
            [PROMPT], SmokeResult, tier=tier, meta=CallMeta(purpose="smoke")
        )
    except AppError as exc:
        print(f"failed: {exc.code} {exc.details}")
        return 1
    finally:
        await provider.aclose()
    print(f"type: {type(result).__name__}")
    print(result.model_dump_json(indent=2))
    print(
        f"model={usage.model} in={usage.tokens_in} out={usage.tokens_out} "
        f"est_cost_usd={estimate_cost(usage)}"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pro", action="store_true", help="use the PRO model")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(ModelTier.PRO if args.pro else ModelTier.FAST)))
