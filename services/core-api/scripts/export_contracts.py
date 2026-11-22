#!/usr/bin/env python3
"""Export event JSON Schemas to packages/contracts/schemas.

Usage:
    python scripts/export_contracts.py          # write
    python scripts/export_contracts.py --check  # CI staleness check
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
OUTPUT_DIR = REPO_ROOT / "packages" / "contracts" / "schemas"

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres")
os.environ.setdefault("INTERNAL_JWT_SECRET", "local-dev-internal-secret-change-me")
os.environ.setdefault("ENVIRONMENT", "test")

sys.path.insert(0, str(ROOT))

from app.events.schemas import (  # noqa: E402
    EVENT_MODELS,
    EventEnvelope,
    NotificationRequestedEvent,
    VerificationCompletedEvent,
    VerificationFailedEvent,
    VerificationRequestedEvent,
)

SCHEMAS = {
    "envelope": EventEnvelope,
    "verification.requested.v1": VerificationRequestedEvent,
    "verification.completed.v1": VerificationCompletedEvent,
    "verification.failed.v1": VerificationFailedEvent,
    "notification.requested.v1": NotificationRequestedEvent,
}


def render() -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, model in SCHEMAS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = name
        rendered[f"{name}.schema.json"] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    index = {
        "version": 1,
        "events": sorted(EVENT_MODELS),
        "files": sorted(f"{name}.schema.json" for name in SCHEMAS),
    }
    rendered["index.json"] = json.dumps(index, indent=2, sort_keys=True) + "\n"
    return rendered


def main() -> int:
    check = "--check" in sys.argv
    rendered = render()
    if check:
        stale = []
        for filename, content in rendered.items():
            path = OUTPUT_DIR / filename
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(filename)
        if stale:
            print("Event contracts are stale: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("Event contracts are up to date")
        return 0
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in rendered.items():
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")
    print(f"Wrote {len(rendered)} files to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
