from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("turn_authority_receipt")
_ALLOWED_VISIBLE_SOURCES = frozenset({"runtime_exact", "runtime_finalized"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha_text(value: str) -> str:
    return hashlib.sha256(str(value or "").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass(slots=True)
class TurnAuthorityReceipt:
    """Cryptographic binding for one user turn and one runtime-owned visible reply.

    The receipt proves software-level binding and authorship policy only. It does
    not prove consciousness, subjective experience, or that a platform host
    invoked the runtime for messages that never reached this process.
    """

    turn_id: str
    trace_id: str
    runtime_version: str
    user_text_sha256: str
    final_visible_text_sha256: str
    identity_canon_sha256: str
    visible_output_source: str
    author_id: str
    author_label: str
    author_source: str
    host_request_contract_hash: str | None = None
    schema_version: str = SCHEMA_VERSION
    receipt_sha256: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("receipt_sha256", None)
        return data

    def calculate_receipt_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.unsigned_dict())).hexdigest()

    def seal(self) -> "TurnAuthorityReceipt":
        self.receipt_sha256 = self.calculate_receipt_sha256()
        return self

    def to_dict(self) -> dict[str, Any]:
        if not self.receipt_sha256:
            self.seal()
        return asdict(self)


def build_turn_authority_receipt(
    *,
    turn_id: str,
    trace_id: str,
    user_text: str | None = None,
    user_text_sha256: str | None = None,
    final_visible_text: str,
    identity_canon_sha256: str,
    visible_output_source: str,
    author_id: str,
    author_label: str,
    author_source: str,
    runtime_version: str = PACKAGE_VERSION_FULL,
    host_request_contract_hash: str | None = None,
) -> dict[str, Any]:
    supplied_user_hash = str(user_text_sha256 or "").lower()
    resolved_user_hash = supplied_user_hash if _SHA256_RE.fullmatch(supplied_user_hash) else _sha_text(user_text or "")
    receipt = TurnAuthorityReceipt(
        turn_id=str(turn_id or ""),
        trace_id=str(trace_id or ""),
        runtime_version=str(runtime_version or PACKAGE_VERSION_FULL),
        user_text_sha256=resolved_user_hash,
        final_visible_text_sha256=_sha_text(final_visible_text),
        identity_canon_sha256=str(identity_canon_sha256 or "").lower(),
        visible_output_source=str(visible_output_source or ""),
        author_id=str(author_id or ""),
        author_label=str(author_label or ""),
        author_source=str(author_source or ""),
        host_request_contract_hash=(str(host_request_contract_hash).lower() if host_request_contract_hash else None),
    ).seal()
    return receipt.to_dict()


def validate_turn_authority_receipt(
    value: Any,
    *,
    expected_user_text: str | None = None,
    expected_user_text_sha256: str | None = None,
    expected_final_visible_text: str | None = None,
    expected_identity_canon_sha256: str | None = None,
    expected_visible_output_source: str | None = None,
) -> dict[str, Any]:
    receipt = dict(value) if isinstance(value, Mapping) else {}
    violations: list[str] = []
    for key in (
        "turn_id", "trace_id", "runtime_version", "user_text_sha256", "final_visible_text_sha256",
        "identity_canon_sha256", "visible_output_source", "author_id", "author_label", "author_source", "receipt_sha256",
    ):
        if not str(receipt.get(key) or "").strip():
            violations.append(f"missing:{key}")
    for key in ("user_text_sha256", "final_visible_text_sha256", "identity_canon_sha256", "receipt_sha256"):
        if receipt.get(key) and not _SHA256_RE.fullmatch(str(receipt.get(key)).lower()):
            violations.append(f"invalid_sha256:{key}")
    host_hash = str(receipt.get("host_request_contract_hash") or "").lower()
    if host_hash and not _SHA256_RE.fullmatch(host_hash):
        violations.append("invalid_sha256:host_request_contract_hash")
    source = str(receipt.get("visible_output_source") or "")
    if source and source not in _ALLOWED_VISIBLE_SOURCES:
        violations.append("visible_output_source_not_runtime_owned")

    unsigned = dict(receipt)
    supplied_receipt_hash = str(unsigned.pop("receipt_sha256", "") or "").lower()
    calculated = hashlib.sha256(_canonical_json(unsigned)).hexdigest() if unsigned else ""
    if supplied_receipt_hash and supplied_receipt_hash != calculated:
        violations.append("receipt_sha256_mismatch")

    expected_user_hash = str(expected_user_text_sha256 or "").lower()
    if not _SHA256_RE.fullmatch(expected_user_hash):
        expected_user_hash = _sha_text(expected_user_text) if expected_user_text is not None else ""
    if expected_user_hash and str(receipt.get("user_text_sha256") or "").lower() != expected_user_hash:
        violations.append("user_text_binding_mismatch")
    if expected_final_visible_text is not None and str(receipt.get("final_visible_text_sha256") or "").lower() != _sha_text(expected_final_visible_text):
        violations.append("final_visible_text_binding_mismatch")
    if expected_identity_canon_sha256 and str(receipt.get("identity_canon_sha256") or "").lower() != str(expected_identity_canon_sha256).lower():
        violations.append("identity_canon_binding_mismatch")
    if expected_visible_output_source and source != expected_visible_output_source:
        violations.append("visible_output_source_binding_mismatch")

    return {
        "ok": not violations,
        "violations": violations,
        "calculated_receipt_sha256": calculated,
        "supplied_receipt_sha256": supplied_receipt_hash,
        "visible_output_source": source or None,
        "schema_version": schema_version("turn_authority_receipt_validation"),
        "truth_boundary": (
            "A valid receipt proves that this runtime bound one exact user-turn digest to one exact visible-reply digest "
            "under the declared identity canon and runtime-owned output source. It cannot prove that an external host "
            "routed messages that never reached the runtime."
        ),
    }
