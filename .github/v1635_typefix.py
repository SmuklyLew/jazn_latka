from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, got {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    presenter = "latka_jazn/core/memory_recall_presenter.py"
    patch(
        presenter,
        "from latka_jazn.core.memory_slot_selector import MemorySlotSelector\n\n@dataclass(slots=True)\n",
        "from latka_jazn.core.memory_slot_selector import MemorySlotSelector\n\n\ndef _dict_copy(value: Any) -> dict[str, Any]:\n    if isinstance(value, dict):\n        return dict(value)\n    return {}\n\n\n@dataclass(slots=True)\n",
    )
    patch(
        presenter,
        '**(hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}),',
        '**_dict_copy(hit.get("metadata")),',
    )

    gateway = "latka_jazn/memory/_living_memory_gateway_impl.py"
    patch(
        gateway,
        'REGISTRY_FILENAME = "memory_source_registry.json"\n\n\n@dataclass(slots=True, frozen=True)\n',
        'REGISTRY_FILENAME = "memory_source_registry.json"\n\n\ndef _optional_float(value: Any) -> float | None:\n    if value is None:\n        return None\n    try:\n        return float(value)\n    except (TypeError, ValueError):\n        return None\n\n\n@dataclass(slots=True, frozen=True)\n',
    )
    patch(
        gateway,
        'confidence=float(row.get("confidence")) if row.get("confidence") is not None else None,\n                    importance=float(row.get("importance")) if row.get("importance") is not None else None,',
        'confidence=_optional_float(row.get("confidence")),\n                    importance=_optional_float(row.get("importance")),',
    )
    print("v16.3.5 strict typing fixes applied")


if __name__ == "__main__":
    main()
