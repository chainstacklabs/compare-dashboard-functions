"""Local verification of an EVM account's MPT proof.

Walks ``accountProof`` returned by ``eth_getProof`` and confirms the leaf is
consistent with a given ``state_root``. Returns the canonical balance on
success; returns ``None`` for canonical exclusion proofs (path divergence,
empty branch slot, etc.); raises ``ProofError`` on real corruption (hash
mismatch, malformed RLP, missing referenced node).

References:
- EIP-1186 (`eth_getProof` API): https://eips.ethereum.org/EIPS/eip-1186
- Yellow paper Appendix C (Hex Prefix encoding) and D (MPT formal definition).
- eth.wiki Patricia Tree primer: https://eth.wiki/fundamentals/patricia-tree
"""

from typing import Any, Optional

import rlp
from Crypto.Hash import keccak


class ProofError(Exception):
    """Raised when the MPT proof is internally inconsistent or malformed.

    Distinct from a canonical exclusion proof — exclusion is signaled by the
    walker returning ``None``, not raising.
    """


def _keccak256(data: bytes) -> bytes:
    """Compute keccak256 (the pre-NIST SHA-3 variant Ethereum uses)."""
    h = keccak.new(digest_bits=256)
    h.update(data)
    digest: bytes = h.digest()
    return digest


def _bytes_to_nibbles(data: bytes) -> list[int]:
    """Split each byte into two 4-bit nibbles (high nibble first)."""
    out: list[int] = []
    for byte in data:
        out.append(byte >> 4)
        out.append(byte & 0x0F)
    return out


def _decode_hp_path(encoded: bytes) -> tuple[list[int], bool]:
    """Decode a Hex-Prefix-encoded path.

    Returns the path nibbles and a ``is_leaf`` flag. Yellow paper Appendix C.

    First-byte high nibble:
    - 0: extension, even-length remainder (skip second nibble — padding).
    - 1: extension, odd-length (second nibble is the first path nibble).
    - 2: leaf, even-length.
    - 3: leaf, odd-length.
    """
    if not encoded:
        raise ProofError("HP-encoded path is empty")
    flag = encoded[0] >> 4
    if flag > 3:
        raise ProofError(f"invalid HP flag nibble: {flag}")
    is_leaf = (flag & 2) != 0
    is_odd = (flag & 1) != 0
    nibbles: list[int] = []
    if is_odd:
        nibbles.append(encoded[0] & 0x0F)
    for byte in encoded[1:]:
        nibbles.append(byte >> 4)
        nibbles.append(byte & 0x0F)
    return nibbles, is_leaf


def _follow_reference(ref: Any, proof_by_hash: dict[bytes, bytes]) -> Any:
    """Resolve a child reference to the next decoded node.

    A child reference is either:
    - A list (already-decoded RLP): an inlined node — used directly. The parent's
      hash already authenticated it, so no separate hash check is required.
    - 32 raw bytes: a hash reference — looked up in ``proof_by_hash``.

    Empty refs (``b""``) signal exclusion at the caller and must not be passed
    here.

    Raises:
        ProofError: If the reference is malformed or its hash isn't in the proof.
    """
    if isinstance(ref, list):
        return ref
    if isinstance(ref, bytes):
        if len(ref) == 32:
            if ref not in proof_by_hash:
                raise ProofError(f"hash {ref.hex()} not present in accountProof")
            return rlp.decode(proof_by_hash[ref])
        raise ProofError(f"reference length {len(ref)} is invalid (must be 0 or 32)")
    raise ProofError(f"unexpected reference type: {type(ref).__name__}")


def _step_branch(
    node: list[Any],
    key_nibbles: list[int],
    path_index: int,
    proof_by_hash: dict[bytes, bytes],
) -> tuple[Any, int, Optional[bytes], bool]:
    """Process a branch node.

    Returns ``(next_node, next_path_index, leaf_value, exclusion)``. Exactly one
    of ``next_node``, ``leaf_value``, or the exclusion flag is the operative
    output; callers branch on whether the walk continues, terminates, or signals
    exclusion.
    """
    if path_index == len(key_nibbles):
        value_at_branch = node[16]
        if not value_at_branch:
            return None, path_index, None, True  # Exclusion: empty terminal value.
        if not isinstance(value_at_branch, bytes):
            raise ProofError("branch terminal value must be bytes")
        return None, path_index, value_at_branch, False

    child_ref = node[key_nibbles[path_index]]
    if child_ref == b"":
        return None, path_index, None, True  # Exclusion: empty branch slot.
    next_node = _follow_reference(child_ref, proof_by_hash)
    return next_node, path_index + 1, None, False


def _step_two_element(
    node: list[Any],
    key_nibbles: list[int],
    path_index: int,
    proof_by_hash: dict[bytes, bytes],
) -> tuple[Any, int, Optional[bytes], bool]:
    """Process an extension or leaf node. Returns same shape as ``_step_branch``."""
    encoded_path, value_or_ref = node
    if not isinstance(encoded_path, bytes):
        raise ProofError("encoded path must be bytes")
    path_nibbles, is_leaf = _decode_hp_path(encoded_path)

    if is_leaf:
        if key_nibbles[path_index:] != path_nibbles:
            return None, path_index, None, True  # Exclusion: leaf divergence.
        if not isinstance(value_or_ref, bytes):
            raise ProofError("leaf value must be bytes")
        return None, path_index, value_or_ref, False

    # Extension.
    end = path_index + len(path_nibbles)
    if key_nibbles[path_index:end] != path_nibbles:
        return None, path_index, None, True  # Exclusion: extension divergence.
    next_node = _follow_reference(value_or_ref, proof_by_hash)
    return next_node, end, None, False


def _decode_account_value(account_value: bytes) -> int:
    """Decode rlp([nonce, balance, storage_hash, code_hash]) and return balance."""
    fields: Any = rlp.decode(account_value)
    if not isinstance(fields, list) or len(fields) != 4:
        raise ProofError(
            f"account leaf has {len(fields) if isinstance(fields, list) else '?'} "
            f"fields, expected 4"
        )
    balance_bytes = fields[1]
    if not isinstance(balance_bytes, bytes):
        raise ProofError("balance field must be bytes")
    return int.from_bytes(balance_bytes, "big") if balance_bytes else 0


def verify_account_proof(
    address: bytes,
    account_proof: list[bytes],
    state_root: bytes,
) -> Optional[int]:
    """Verify an MPT account proof and return the canonical balance.

    Args:
        address: 20-byte EVM address.
        account_proof: List of RLP-encoded MPT nodes from ``eth_getProof.accountProof``.
        state_root: 32-byte state root (the trusted anchor).

    Returns:
        The balance as a Python int on success, or ``None`` if the address has
        no state at this block (canonical exclusion proof).

    Raises:
        ProofError: If the proof is invalid (hash mismatch, malformed RLP,
            missing referenced node, etc.). Distinct from exclusion.
    """
    if len(address) != 20:
        raise ProofError(f"address must be 20 bytes, got {len(address)}")
    if len(state_root) != 32:
        raise ProofError(f"state_root must be 32 bytes, got {len(state_root)}")

    # Build hash → rlp lookup so traversal doesn't depend on proof array order.
    proof_by_hash: dict[bytes, bytes] = {
        _keccak256(node_rlp): node_rlp for node_rlp in account_proof
    }

    if state_root not in proof_by_hash:
        # Empty trie — canonical exclusion (also possible for a brand-new chain).
        return None

    key_nibbles = _bytes_to_nibbles(_keccak256(address))
    current_node: Any = rlp.decode(proof_by_hash[state_root])
    path_index = 0
    account_value: Optional[bytes] = None

    while True:
        if isinstance(current_node, list) and len(current_node) == 17:
            current_node, path_index, leaf, excluded = _step_branch(
                current_node, key_nibbles, path_index, proof_by_hash
            )
        elif isinstance(current_node, list) and len(current_node) == 2:
            current_node, path_index, leaf, excluded = _step_two_element(
                current_node, key_nibbles, path_index, proof_by_hash
            )
        else:
            raise ProofError(f"unexpected node shape: {current_node!r}")

        if excluded:
            return None
        if leaf is not None:
            account_value = leaf
            break

    if account_value is None:
        return None
    return _decode_account_value(account_value)
