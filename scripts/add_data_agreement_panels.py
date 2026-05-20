"""Insert a Data agreement row into hyperliquid/solana/ton dashboards.

Template is Monad's existing Data agreement row. We swap:
- blockchain tag value
- metric_type (balance_observed for HL EVM; account_observed for SOL/TON)
- panel descriptions (per chain + global vs regional)
- source_region pin (regional only)
- panel + row IDs (unique per chain)
- gridPos.y (insert after Block lag row, bump everything below)
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DASH_DIR = Path(__file__).resolve().parents[1] / "dashboards" / "dashboards"
MONAD_GLOBAL = DASH_DIR / "compare-dashboard-monad.json"
MONAD_EU = DASH_DIR / "compare-dashboard-monad-eu.json"


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text())


def dump(p: Path, d: dict[str, Any]) -> None:
    p.write_text(json.dumps(d, indent=2) + "\n")


def find_row_index(dash: dict[str, Any], title: str) -> int:
    for i, p in enumerate(dash["panels"]):
        if p.get("type") == "row" and p.get("title") == title:
            return i
    raise ValueError(f"row '{title}' not found")


def extract_monad_row(monad: dict[str, Any]) -> dict[str, Any]:
    idx = find_row_index(monad, "Data agreement")
    return copy.deepcopy(monad["panels"][idx])


# Chain → (blockchain tag, metric_type, observation_phrase, probe_phrase)
CHAINS = {
    "hyperliquid": {
        "blockchain": "Hyperliquid",
        "metric_type": "balance_observed",
        "observation_global": "eth_getBalance for the WHYPE token contract at the probe block",
        "observation_regional": "eth_getBalance for the WHYPE token contract at the probe block",
        "id_base": 700,
    },
    "solana": {
        "blockchain": "Solana",
        "metric_type": "account_observed",
        "observation_global": "getAccountInfo for the USDC mint, pinned to the probe slot via minContextSlot",
        "observation_regional": "getAccountInfo for the USDC mint, pinned to the probe slot via minContextSlot",
        "id_base": 720,
    },
    "ton": {
        "blockchain": "TON",
        "metric_type": "account_observed",
        "observation_global": "runGetMethod(get_jetton_data) on the USDT master, pinned to the probe seqno",
        "observation_regional": "runGetMethod(get_jetton_data) on the USDT master, pinned to the probe seqno",
        "id_base": 740,
    },
}

REGION_NAMES = {
    "fra1": "EU",
    "sfo1": "US West",
    "sin1": "SG",
    "hnd1": "Japan",
}


# (filename suffix, source_region or None for global)
DASH_TARGETS = {
    "hyperliquid": [
        ("compare-dashboard-hyperliquid.json", None),
        ("compare-dashboard-hyperliquid-eu.json", "fra1"),
        ("compare-dashboard-hyperliquid-japan.json", "hnd1"),
        ("compare-dashboard-hyperliquid-us-west.json", "sfo1"),
    ],
    "solana": [
        ("compare-dashboard-solana.json", None),
        ("compare-dashboard-solana-eu.json", "fra1"),
        ("compare-dashboard-solana-singapore.json", "sin1"),
        ("compare-dashboard-solana-us-west.json", "sfo1"),
    ],
    "ton": [
        ("compare-dashboard-ton.json", None),
        ("compare-dashboard-ton-eu.json", "fra1"),
        ("compare-dashboard-ton-singapore.json", "sin1"),
    ],
}


def rewrite_global_row(
    row: dict[str, Any],
    chain: dict[str, Any],
    row_y: int,
) -> dict[str, Any]:
    """Adapt the Monad GLOBAL Data agreement row for the target chain."""
    blockchain = chain["blockchain"]
    metric_type = chain["metric_type"]
    obs = chain["observation_global"]
    base = chain["id_base"]

    row["id"] = base
    row["gridPos"]["y"] = row_y
    inner_y = row_y + 2

    timeline, summary = row["panels"]
    timeline["id"] = base + 1
    timeline["gridPos"]["y"] = inner_y
    timeline["description"] = (
        f"Per provider, did this provider's {obs} match the majority answer "
        "in every region it participated in at this moment. Green - matched "
        "the majority everywhere. Red - was an outlier in at least one region. "
        "Grey - no data captured."
    )
    summary["id"] = base + 2
    summary["gridPos"]["y"] = inner_y
    summary["description"] = (
        f"For each provider in each region, the percentage of samples "
        f"({obs}) that matched the majority answer for the same block, "
        "over the chosen time range. 100% means always agreed with the "
        "majority. Sorted highest first."
    )

    for tgt in timeline["targets"]:
        tgt["expr"] = (
            tgt["expr"]
            .replace('metric_type="balance_observed"', f'metric_type="{metric_type}"')
            .replace('blockchain="Monad"', f'blockchain="{blockchain}"')
        )
    for tgt in summary["targets"]:
        tgt["expr"] = (
            tgt["expr"]
            .replace('metric_type="balance_observed"', f'metric_type="{metric_type}"')
            .replace('blockchain="Monad"', f'blockchain="{blockchain}"')
        )
    return row


def rewrite_regional_row(
    row: dict[str, Any],
    chain: dict[str, Any],
    row_y: int,
    source_region: str,
) -> dict[str, Any]:
    """Adapt the Monad REGIONAL Data agreement row for the target chain + region."""
    blockchain = chain["blockchain"]
    metric_type = chain["metric_type"]
    obs = chain["observation_regional"]
    base = chain["id_base"]
    region_name = REGION_NAMES[source_region]

    row["id"] = base
    row["gridPos"]["y"] = row_y
    inner_y = row_y + 2

    timeline, summary = row["panels"]
    timeline["id"] = base + 1
    timeline["gridPos"]["y"] = inner_y
    timeline["description"] = (
        f"Per provider in this region ({region_name}), did this provider's "
        f"{obs} match the majority answer for the same block at this moment. "
        "Green - matched the majority. Red - was an outlier. Grey - no data "
        "captured."
    )
    summary["id"] = base + 2
    summary["gridPos"]["y"] = inner_y
    summary["description"] = (
        f"For each provider in this region ({region_name}), the percentage "
        f"of samples ({obs}) that matched the majority answer for the same "
        "block, over the chosen time range. 100% means always agreed with "
        "the majority. Sorted highest first."
    )

    for tgt in timeline["targets"]:
        # Monad regional template uses source_region="fra1"; swap region + chain.
        tgt["expr"] = (
            tgt["expr"]
            .replace('metric_type="balance_observed"', f'metric_type="{metric_type}"')
            .replace('blockchain="Monad"', f'blockchain="{blockchain}"')
            .replace('source_region="fra1"', f'source_region="{source_region}"')
        )
    for tgt in summary["targets"]:
        tgt["expr"] = (
            tgt["expr"]
            .replace('metric_type="balance_observed"', f'metric_type="{metric_type}"')
            .replace('blockchain="Monad"', f'blockchain="{blockchain}"')
            .replace('source_region="fra1"', f'source_region="{source_region}"')
        )
    return row


def insert_into_dashboard(
    dash_path: Path,
    chain: dict[str, Any],
    source_region: str | None,
    monad_global_row: dict[str, Any],
    monad_regional_row: dict[str, Any],
) -> None:
    dash = load(dash_path)

    # Remove pre-existing Data agreement row (idempotent re-runs).
    dash["panels"] = [
        p
        for p in dash["panels"]
        if not (p.get("type") == "row" and p.get("title") == "Data agreement")
    ]

    block_lag_idx = find_row_index(dash, "Block lag")
    block_lag_y = dash["panels"][block_lag_idx]["gridPos"]["y"]
    insert_y = block_lag_y + 1

    # Bump y of every panel whose y >= insert_y.
    for p in dash["panels"]:
        if p["gridPos"]["y"] >= insert_y:
            p["gridPos"]["y"] += 1

    if source_region is None:
        new_row = rewrite_global_row(copy.deepcopy(monad_global_row), chain, insert_y)
    else:
        new_row = rewrite_regional_row(
            copy.deepcopy(monad_regional_row), chain, insert_y, source_region
        )

    dash["panels"].insert(block_lag_idx + 1, new_row)
    dump(dash_path, dash)
    kind = "global" if source_region is None else f"regional ({source_region})"
    print(f"[ok] {dash_path.name} — inserted Data agreement {kind} row")


def main() -> None:
    monad_global = load(MONAD_GLOBAL)
    monad_eu = load(MONAD_EU)
    monad_global_row = extract_monad_row(monad_global)
    monad_regional_row = extract_monad_row(monad_eu)

    for chain_key, targets in DASH_TARGETS.items():
        chain = CHAINS[chain_key]
        for filename, source_region in targets:
            insert_into_dashboard(
                DASH_DIR / filename,
                chain,
                source_region,
                monad_global_row,
                monad_regional_row,
            )


if __name__ == "__main__":
    main()
