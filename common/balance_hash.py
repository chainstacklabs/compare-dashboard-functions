"""Hash uint256 balances to 52-bit floats for Influx/Mimir storage.

Grafana Cloud's Prometheus-compatible store accepts only float64 samples.
Ethereum balances are uint256 and routinely exceed 2^53, so direct float
storage silently rounds and breaks equality. We SHA-256 the decimal-string
form and keep the low 52 bits — exactly representable in float64 (integers
up to 2^53 are exact). Identical inputs produce identical floats; collisions
are ~1 / 4.5e15 per comparison.

The decimal string is the shared form: v1 hashes int(hex_result, 16); v2's
MPT verifier produces the int from RLP. Both decimal-stringify before hashing
so observed and verified samples match when underlying balances match.
"""

import hashlib

_MASK_52: int = 0x0F_FFFF_FFFF_FFFF


def hash_balance_to_float(balance: int) -> float:
    """Hash a uint256 balance to a 52-bit float64.

    Args:
        balance: The balance value as a Python int.

    Returns:
        The low 52 bits of ``sha256(str(balance))`` as a float, exactly
        representable in float64.

    Raises:
        ValueError: If ``balance`` is negative.
    """
    if balance < 0:
        raise ValueError(f"balance must be non-negative, got {balance}")
    digest: bytes = hashlib.sha256(str(balance).encode("utf-8")).digest()
    return float(int.from_bytes(digest[:7], "big") & _MASK_52)


def hash_bytes_to_float(payload: bytes) -> float:
    """Hash an arbitrary byte string to a 52-bit float64.

    Same shape and collision profile as ``hash_balance_to_float``, but skips
    the decimal-string step so callers can hash a canonicalised account-state
    blob (e.g. Solana ``getAccountInfo`` fields) without first deriving an
    int. Identical inputs produce identical floats.

    Args:
        payload: Canonicalised account-state bytes.

    Returns:
        The low 52 bits of ``sha256(payload)`` as a float, exactly
        representable in float64.
    """
    digest: bytes = hashlib.sha256(payload).digest()
    return float(int.from_bytes(digest[:7], "big") & _MASK_52)
