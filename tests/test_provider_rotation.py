"""Self-check for provider rotation: python tests/test_provider_rotation.py

Fails if the lead position is not shared evenly, if the ordering is unstable
within a single cron period, or if rotation loses/duplicates a provider.
"""

import collections
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.metrics_handler import rotate_providers
from config.defaults import MetricsServiceConfig

P = MetricsServiceConfig.CRON_PERIOD_SECONDS


def providers(n: int) -> list[dict[str, Any]]:
    return [{"name": f"p{i}"} for i in range(n)]


def main() -> None:
    base = 1_786_000_000.0

    # 1. Every provider leads an equal share of rounds.
    for n in (2, 3, 4, 5):
        ps = providers(n)
        leads = collections.Counter(
            rotate_providers(ps, base + r * P)[0]["name"] for r in range(n * 50)
        )
        assert len(leads) == n, f"only {len(leads)} of {n} providers ever led"
        assert set(leads.values()) == {50}, f"uneven lead share for n={n}: {leads}"

    # 2. Ordering is stable within a period — every metric in one round must
    #    agree, otherwise providers interleave unpredictably.
    ps = providers(4)
    start = (base // P) * P
    within = {
        tuple(p["name"] for p in rotate_providers(ps, start + off))
        for off in (0, 1, 30, 90, P - 1)
    }
    assert len(within) == 1, f"ordering changed inside one cron period: {within}"

    # 3. Consecutive periods advance the lead by exactly one, cyclically.
    #    (The absolute starting lead depends on the epoch, so assert the step
    #    rather than a hardcoded first element.)
    order = [p["name"] for p in ps]
    seq = [rotate_providers(ps, start + r * P)[0]["name"] for r in range(len(ps) + 1)]
    for a, b in zip(seq, seq[1:]):
        expected = order[(order.index(a) + 1) % len(order)]
        assert b == expected, f"lead went {a} -> {b}, expected {expected}: {seq}"
    assert seq[0] == seq[-1], f"lead did not return after a full cycle: {seq}"

    # 4. Rotation is a permutation — nothing lost, added or duplicated.
    for r in range(8):
        out = rotate_providers(ps, base + r * P)
        assert sorted(p["name"] for p in out) == sorted(p["name"] for p in ps)
        assert len(out) == len(ps)

    # 5. Degenerate inputs are returned untouched.
    assert rotate_providers([], base) == []
    one = providers(1)
    assert rotate_providers(one, base) == one

    print(
        "OK: lead position rotates evenly, is stable within a round, "
        "and preserves the provider set"
    )


main()
