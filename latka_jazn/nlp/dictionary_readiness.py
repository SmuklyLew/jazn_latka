from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.nlp.polish_lexical_sources import MINI_LEXICON
from latka_jazn.nlp.providers.optional_morfeusz_provider import (
    OptionalMorfeuszProvider,
)
from latka_jazn.nlp.providers.plwordnet_optional_provider import (
    PlWordNetOptionalProvider,
)
from latka_jazn.nlp.providers.sjp_reference_provider import SJPReferenceProvider
from latka_jazn.nlp.providers.wsjp_reference_provider import WSJPReferenceProvider
from latka_jazn.version import schema_version


def _builtin_probe() -> dict[str, Any]:
    sample_term = next(iter(MINI_LEXICON), "")
    sample = MINI_LEXICON.get(sample_term) if sample_term else None
    sample_map = sample if isinstance(sample, dict) else {}
    probe_ok = bool(
        sample_term
        and list(sample_map.get("lemma") or [])
        and list(sample_map.get("definitions") or [])
    )
    return {
        "provider": "local_jazn_mini_lexicon",
        "kind": "embedded_local_lookup",
        "installed": bool(MINI_LEXICON),
        "configured": True,
        "license_verified": True,
        "provenance_ok": probe_ok,
        "last_probe_ok": probe_ok,
        "probe_scope": "read_only_in_process_sample",
        "lookup_ready": probe_ok,
        "status": "ready" if probe_ok else "embedded_lexicon_probe_failed",
    }


def _cache_probe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "provider": "local_cache",
            "kind": "sqlite_cache",
            "installed": False,
            "configured": True,
            "cache_ready": False,
            "last_probe_ok": False,
            "lookup_ready": False,
            "status": "not_initialized",
        }
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        ready = {"dictionary_entries", "lookup_events"}.issubset(tables)
        status = "ready" if ready else "schema_incomplete"
    except sqlite3.Error as exc:
        ready = False
        status = f"read_only_probe_failed:{type(exc).__name__}"
    return {
        "provider": "local_cache",
        "kind": "sqlite_cache",
        "installed": True,
        "configured": True,
        "cache_ready": ready,
        "last_probe_ok": ready,
        "lookup_ready": ready,
        "status": status,
    }


def _morfeusz_probe(configured: bool) -> dict[str, Any]:
    provider = OptionalMorfeuszProvider()
    result = provider.lookup("kot", "pl") if provider.available else None
    probe_ok = bool(
        result is not None
        and result.status == "ok"
        and result.lemmas
    )
    return {
        "provider": provider.name,
        "kind": "optional_local_morphology",
        "installed": provider.available,
        "configured": configured,
        "license_verified": None,
        "provenance_ok": None,
        "last_probe_ok": probe_ok if provider.available else False,
        "lookup_ready": bool(configured and probe_ok),
        "status": (
            "ready"
            if configured and probe_ok
            else str(result.status)
            if result is not None
            else "not_installed"
        ),
    }


def _plwordnet_probe(root: Path, configured: bool) -> dict[str, Any]:
    provider = PlWordNetOptionalProvider(root)
    installed = provider.index_path.is_file()
    metadata: dict[str, Any] = {}
    if provider.metadata_path.is_file():
        try:
            value = json.loads(provider.metadata_path.read_text(encoding="utf-8"))
            metadata = value if isinstance(value, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            metadata = {}
    result = provider.lookup("kot", "pl") if installed else None
    probe_ok = bool(result and result.status in {"ok", "not_found"})
    license_verified = bool(str(metadata.get("license_note") or "").strip())
    return {
        "provider": provider.name,
        "kind": "optional_local_lexico_semantic_index",
        "installed": installed,
        "configured": configured,
        "license_verified": license_verified if installed else None,
        "provenance_ok": bool(metadata) if installed else None,
        "last_probe_ok": probe_ok if installed else False,
        "lookup_ready": bool(configured and probe_ok and license_verified),
        "status": (
            "ready"
            if configured and probe_ok and license_verified
            else str(result.status)
            if result is not None
            else "not_installed"
        ),
    }


def _reference_probe(provider: Any, *, configured: bool) -> dict[str, Any]:
    result = provider.lookup("kot", "pl")
    reference_ready = bool(
        configured
        and result.status == "manual_reference_available"
        and str(result.source_url or "").startswith("https://")
    )
    return {
        "provider": provider.name,
        "kind": "manual_reference_link",
        "configured": configured,
        "network_allowed": False,
        "reference_ready": reference_ready,
        "last_probe_ok": reference_ready,
        "lookup_ready": False,
        "status": "reference_ready" if reference_ready else result.status,
        "truth_boundary": "Reference readiness is not dictionary lookup readiness.",
    }


def build_dictionary_readiness_status(cfg: JaznConfig) -> dict[str, Any]:
    """Probe lookup capabilities without network access or cache creation."""

    provider_order = tuple(cfg.dictionary_provider_order)
    cache = _cache_probe(cfg.lexical_resource_cache_path)
    providers = [
        cache,
        _builtin_probe(),
        _morfeusz_probe("morfeusz_optional" in provider_order),
        _plwordnet_probe(
            Path(cfg.root),
            "plwordnet_optional" in provider_order,
        ),
        {
            "provider": "wiktionary_mediawiki_api",
            "kind": "network_dictionary",
            "configured": "wiktionary_mediawiki_api" in provider_order,
            "network_allowed": cfg.dictionary_allow_network,
            "reachable": None,
            "cache_ready": cache["cache_ready"],
            "last_probe_ok": None,
            "last_success_utc": None,
            "license_verified": None,
            "license_status": "declared_policy_not_live_verified",
            "provenance_ok": None,
            "lookup_ready": False,
            "status": "not_probed_read_only_status",
        },
        _reference_probe(
            SJPReferenceProvider(),
            configured="sjp_reference" in provider_order,
        ),
        _reference_probe(
            WSJPReferenceProvider(),
            configured="wsjp_reference" in provider_order,
        ),
    ]
    ready_providers = [
        str(provider["provider"])
        for provider in providers
        if provider.get("lookup_ready") is True
    ]
    return {
        "schema_version": schema_version("dictionary_provider_status"),
        "provider_order": list(provider_order),
        "probe_mode": "read_only_no_network",
        "providers": providers,
        "dictionary_lookup_ready": bool(ready_providers),
        "dictionary_lookup_scope": "at_least_one_capability_specific_provider",
        "ready_lookup_providers": ready_providers,
        "external_failure_policy": "fail_soft",
        "external_failure_blocks_voice": False,
        "truth_boundary": (
            "dictionary_lookup_ready requires a successful capability-specific "
            "read-only probe. Module or adapter file presence is never sufficient. "
            "Network reachability remains unknown until an explicit lookup probes it."
        ),
    }


__all__ = ["build_dictionary_readiness_status"]
