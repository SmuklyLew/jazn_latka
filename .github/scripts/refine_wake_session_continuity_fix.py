from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one source block, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> None:
    wake = Path("latka_jazn/memory/wake_state_runtime.py")
    replace_once(
        wake,
        "            source_path = self.config.normalization_source_db_path\n",
        "            # Self-repair is allowed only from the immutable recovered snapshot.\n"
        "            # The mutable runtime-write DB is not a substitute for recovered memory:\n"
        "            # using it here would create a derived wake snapshot from ordinary turn writes\n"
        "            # and would make the sidecar stale again as soon as those writes changed.\n"
        "            source_path = self.config.recovered_memory_db_path\n",
        "recovered_source_only",
    )

    tests = Path("tests/test_wake_session_continuity_decoupling.py")
    replace_once(
        tests,
        "    _source(cfg.normalization_source_db_path)\n",
        "    _source(cfg.recovered_memory_db_path)\n",
        "repair_test_recovered_source",
    )
    replace_once(
        tests,
        "    assert not cfg.normalization_source_db_path.exists()\n    assert not cfg.normalization_sidecar_db_path.exists()\n",
        "    assert not cfg.recovered_memory_db_path.exists()\n    assert not cfg.normalization_sidecar_db_path.exists()\n",
        "no_source_test_recovered_source",
    )

    report = Path("docs/reports/WAKE_SESSION_CONTINUITY_HARDENING.md")
    replace_once(
        report,
        "when the verified local recovery source database already existed.",
        "when the verified local recovered-memory snapshot already existed.",
        "report_problem_source",
    )
    replace_once(
        report,
        "only when `normalization_source_db_path` already exists locally. Repair delegates to",
        "only when the immutable `recovered_memory_db_path` already exists locally. The mutable runtime-write database is deliberately not accepted as a repair source. Repair delegates to",
        "report_repair_source",
    )


if __name__ == "__main__":
    main()
