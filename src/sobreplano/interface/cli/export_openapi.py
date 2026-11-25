"""Write the API contract to web/src/lib/api/openapi.json, the source of the web client types."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.main import create_app

# src/sobreplano/interface/cli/export_openapi.py → the repository root.
REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = REPO_ROOT / "web" / "src" / "lib" / "api" / "openapi.json"
# The schema does not depend on the database; this URL is never opened.
UNUSED_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"


def render_contract() -> str:
    """The OpenAPI document of the app as stable text: sorted keys, indent 2, final newline.

    Built from the code, not from /openapi.json, which production turns off (SPEC 10).
    """
    schema: dict[str, Any] = create_app(Settings(database_url=UNUSED_URL)).openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the contract; with --check, exit 1 if the file in the repo differs instead."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="compare with the file in the repo, write nothing"
    )
    args = parser.parse_args(argv)
    contract = render_contract()
    if args.check:
        current = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else None
        if current != contract:
            print(f"{CONTRACT_PATH} is out of date; run export_openapi without --check")
            return 1
        print(f"{CONTRACT_PATH} is up to date")
        return 0
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(contract, encoding="utf-8")
    print(f"wrote {CONTRACT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
