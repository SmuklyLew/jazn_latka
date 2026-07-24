from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from latka_jazn.version import schema_version

CURRENT_CONTRACT_SOURCES = (
    "AGENTS.md",
    "AGENTS.chatgpt.md",
    "AGENTS.codex.md",
    "AGENTS.ollama.md",
    "README.md",
    "latka_jazn/resources/chatgpt_startup_loader.txt",
    "latka_jazn/resources/startup_contract.json",
)


class BootstrapContractRepository:
    """Read current bootstrap contracts from the active source tree only.

    Historical or private generated sources are never executable fallbacks.
    Missing files remain visibly missing and fail closed in diagnostics.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def get_text(self, relative_path: str) -> str | None:
        path = self.root / relative_path
        if not path.exists() or not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def status(self) -> dict[str, Any]:
        present: list[dict[str, Any]] = []
        missing: list[str] = []
        for rel in CURRENT_CONTRACT_SOURCES:
            path = self.root / rel
            if path.is_file():
                raw = path.read_bytes()
                present.append({"path": rel, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)})
            else:
                missing.append(rel)
        return {
            "schema_version": schema_version("bootstrap_contract_repository"),
            "source_policy": "current_files_only",
            "configured_source_count": len(CURRENT_CONTRACT_SOURCES),
            "present_source_count": len(present),
            "missing_source_count": len(missing),
            "present_sources": present,
            "missing_sources": missing,
            "ok": not missing,
            "truth_boundary": (
                "Repository reads only current reviewed files. Historical and private generated sources "
                "are not fallback dialogue or executable contracts."
            ),
        }

    def summary_text(self, limit: int = 20) -> str:
        status = self.status()
        status["present_sources"] = status["present_sources"][:limit]
        return json.dumps(status, ensure_ascii=False, indent=2)
