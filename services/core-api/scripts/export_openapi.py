#!/usr/bin/env python3
"""Export the public OpenAPI contract to docs/api/openapi.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
OUTPUT = REPO_ROOT / "docs" / "api" / "openapi.json"

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres")
os.environ.setdefault("INTERNAL_JWT_SECRET", "local-dev-internal-secret-change-me")
os.environ.setdefault("ENVIRONMENT", "test")

sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    content = render()
    if check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            print(f"OpenAPI contract is stale: {OUTPUT}", file=sys.stderr)
            return 1
        print("OpenAPI contract is up to date")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
