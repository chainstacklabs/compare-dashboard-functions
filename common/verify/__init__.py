"""Verifier package: multi-provider stateRoot quorum + MPT proof verification.

See ``spec-verified-correctness-v2.md`` (local design doc) for the full design.
"""

from common.verify.anchor import (
    AnchorDisagreementError,
    AnchorError,
    AnchorPartialResponseError,
    fetch_account_proof,
    fetch_agreed_anchor,
)
from common.verify.proof import ProofError, verify_account_proof
from common.verify.providers import all_providers_for, chainstack_endpoint_for

__all__ = [
    "AnchorDisagreementError",
    "AnchorError",
    "AnchorPartialResponseError",
    "ProofError",
    "all_providers_for",
    "chainstack_endpoint_for",
    "fetch_account_proof",
    "fetch_agreed_anchor",
    "verify_account_proof",
]
