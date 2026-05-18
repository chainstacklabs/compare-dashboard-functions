"""End-to-end smoke test for v2.1 verify_state.

Runs `_verify_all` locally against the live endpoints in endpoints.json
and prints the resulting Influx lines. Does NOT push to Grafana.
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["ENDPOINTS"] = (ROOT / "endpoints.json").read_text()
sys.path.insert(0, str(ROOT))

from api.support.verify_state import _verify_all  # noqa: E402


async def main() -> None:
    out = await _verify_all()
    print(out)


if __name__ == "__main__":
    asyncio.run(main())
