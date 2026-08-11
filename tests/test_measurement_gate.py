"""Self-check for the measurement gate: python tests/test_measurement_gate.py

Fails if serialised metrics ever overlap, if exempt metrics get serialised,
if a hung metric can consume the whole round, or if a metric the budget
starved before it started gets wrongly reported as a provider failure.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.base_metric import BaseMetric
from common.metric_config import MetricLabels
from common.metrics_handler import MetricsHandler

WORK = 0.05

Span = tuple[float, float]


class FakeMetric:
    def __init__(
        self, log: list[Span], *, serialise: bool = True, work: float = WORK
    ) -> None:
        self.serialise_measurement = serialise
        self.log = log
        self.work = work
        self.failed = False
        self.labels = MetricLabels(
            source_region="test",
            target_region="test",
            blockchain="test",
            provider="test",
        )

    async def collect_metric(self) -> None:
        start: float = time.monotonic()
        await asyncio.sleep(self.work)
        self.log.append((start, time.monotonic()))

    def mark_failure(self) -> None:
        self.failed = True

    def handle_error(self, error: Exception) -> None:
        pass


async def collect_one(
    metric: FakeMetric, gate: asyncio.Semaphore, deadline: float
) -> None:
    """Adapt FakeMetric (duck-typed, not a BaseMetric subclass) for the gate."""
    await MetricsHandler._collect_one(cast(BaseMetric, metric), gate, deadline)


def overlaps(spans: list[Span]) -> bool:
    spans = sorted(spans)
    return any(spans[i][1] > spans[i + 1][0] + 1e-6 for i in range(len(spans) - 1))


async def main() -> None:
    # 1. Serialised metrics never overlap, even when gathered together.
    log: list[Span] = []
    metrics = [FakeMetric(log) for _ in range(8)]
    gate = asyncio.Semaphore(1)
    deadline = time.monotonic() + 30
    await asyncio.gather(*(collect_one(m, gate, deadline) for m in metrics))
    assert len(log) == 8, f"expected 8 measurements, got {len(log)}"
    assert not overlaps(log), "serialised measurements overlapped -> contention"
    assert not any(m.failed for m in metrics), "healthy metrics were marked failed"

    # 2. Exempt (WebSocket) metrics bypass the gate and run concurrently.
    ws_log: list[Span] = []
    ws = [FakeMetric(ws_log, serialise=False) for _ in range(4)]
    gate = asyncio.Semaphore(1)
    started = time.monotonic()
    await asyncio.gather(*(collect_one(m, gate, time.monotonic() + 30) for m in ws))
    assert time.monotonic() - started < WORK * 2, "exempt metrics were serialised"

    # 3. A hung metric burns only the remaining budget and is marked failed;
    #    a metric starved before it even started emits nothing — it must not
    #    read as a provider failure it did not cause.
    hung = FakeMetric([], work=30)
    after = FakeMetric([])
    gate = asyncio.Semaphore(1)
    deadline = time.monotonic() + 0.2
    started = time.monotonic()
    await asyncio.gather(
        collect_one(hung, gate, deadline),
        collect_one(after, gate, deadline),
    )
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"budget not enforced: round took {elapsed:.2f}s"
    assert hung.failed, "hung metric was not marked failed"
    assert not after.failed, "starved metric was wrongly marked as a failure"
    assert not after.log, "starved metric ran despite an exhausted budget"

    # 4. Gate-EXEMPT metrics are bounded by the deadline too. Their own timeout
    #    (METRIC_REQUEST_TIMEOUT, 55s) exceeds the budget, so leaving them
    #    unbounded would blow the function's maxDuration and lose the round.
    hung_ws = FakeMetric([], serialise=False, work=30)
    gate = asyncio.Semaphore(1)
    started = time.monotonic()
    await collect_one(hung_ws, gate, time.monotonic() + 0.2)
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"exempt metric ignored the budget: took {elapsed:.2f}s"
    assert hung_ws.failed, "hung exempt metric was not marked failed"

    print("OK: measurement gate serialises, exempts WS, and honours the budget")


asyncio.run(main())
