from __future__ import annotations

from pathlib import Path

BRANCH = "fix/v16.3.1-host-finalization-provenance-polish-nlp"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


def main() -> None:
    replace_once(
        Path("main.py"),
        '            client="chatgpt_bridge_one_shot_daemon_fast_path",\n',
        '            client="chatgpt_daemon_bridge",\n',
    )
    replace_once(
        Path("latka_jazn/core/chat_command_contract.py"),
        "from latka_jazn.core.host_regeneration_policy import decide_host_regeneration\n",
        "from latka_jazn.core.host_regeneration_policy import decide_host_regeneration\n"
        "from latka_jazn.core.epistemic_evidence import host_tool_attestations_to_external_evidence\n",
    )
    replace_once(
        Path("latka_jazn/core/chat_command_contract.py"),
        '                memory_evidence={\n'
        '                    "memory_source_ids": list(reply.get("used_memory_item_ids") or []),\n'
        '                },\n'
        '            )\n',
        '                memory_evidence={\n'
        '                    "memory_source_ids": list(reply.get("used_memory_item_ids") or []),\n'
        '                },\n'
        '                external_evidence=host_tool_attestations_to_external_evidence(\n'
        '                    semantic_validation.get("external_tool_evidence") or []\n'
        '                ),\n'
        '            )\n',
    )
    Path("tools/_v1631_finalize_branch.py").unlink()
    Path(".github/workflows/v1631-branch-finalizer.yml").unlink()


if __name__ == "__main__":
    main()
