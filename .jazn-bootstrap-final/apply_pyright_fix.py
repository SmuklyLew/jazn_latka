from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected exactly one match for {old!r}, got {text.count(old)}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def insert_once(path: str, marker: str, insertion: str) -> None:
    replace_once(path, marker, marker + insertion)


insert_once(
    "latka_jazn/dependencies/environment.py",
    "from .wheelhouse import discover_bundles, read_manifest, sha256_file, verify_bundle\n",
    "\n\ndef _mapping(value: Any) -> Mapping[str, Any]:\n    return value if isinstance(value, Mapping) else {}\n",
)
replace_once("latka_jazn/dependencies/environment.py", 'metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}', 'metadata = _mapping(item.get("metadata"))')
replace_once("latka_jazn/dependencies/environment.py", 'target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}', 'target = _mapping(manifest.get("target"))')
replace_once("latka_jazn/dependencies/environment.py", 'managed = status.get("managed_environment") if isinstance(status.get("managed_environment"), dict) else {}', 'managed = _mapping(status.get("managed_environment"))')

replace_once("latka_jazn/dependencies/release_artifact.py", "from typing import Any", "from typing import Any, Mapping")
insert_once(
    "latka_jazn/dependencies/release_artifact.py",
    "from .common import DEPENDENCY_SET_NAME, default_wheelhouse_root, target_spec\n",
    "\n\ndef _mapping(value: Any) -> Mapping[str, Any]:\n    return value if isinstance(value, Mapping) else {}\n\n\ndef _list(value: Any) -> list[Any]:\n    return value if isinstance(value, list) else []\n",
)
replace_once("latka_jazn/dependencies/release_artifact.py", 'entries = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []', 'entries = _list(payload.get("artifacts"))')
replace_once("latka_jazn/dependencies/release_artifact.py", 'target = raw.get("target") if isinstance(raw.get("target"), dict) else {}', 'target = _mapping(raw.get("target"))')

replace_once("latka_jazn/dependencies/wheelhouse.py", "from typing import Any, Sequence", "from typing import Any, Mapping, Sequence")
insert_once(
    "latka_jazn/dependencies/wheelhouse.py",
    "    runtime_version,\n    target_spec,\n)\n",
    "\n\ndef _mapping(value: Any) -> Mapping[str, Any]:\n    return value if isinstance(value, Mapping) else {}\n\n\ndef _list(value: Any) -> list[Any]:\n    return value if isinstance(value, list) else []\n",
)
p = Path("latka_jazn/dependencies/wheelhouse.py")
text = p.read_text(encoding="utf-8")
old = 'target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}'
if text.count(old) != 2:
    raise SystemExit(f"wheelhouse.py: expected 2 target matches, got {text.count(old)}")
text = text.replace(old, 'target = _mapping(manifest.get("target"))')
old = 'files = manifest.get("files") if isinstance(manifest.get("files"), list) else []'
if text.count(old) != 1:
    raise SystemExit("wheelhouse.py: files marker mismatch")
text = text.replace(old, 'files = _list(manifest.get("files"))', 1)
old = 'resolved = manifest.get("resolved_distributions") if isinstance(manifest.get("resolved_distributions"), list) else []'
if text.count(old) != 1:
    raise SystemExit("wheelhouse.py: resolved marker mismatch")
text = text.replace(old, 'resolved = _list(manifest.get("resolved_distributions"))', 1)
p.write_text(text, encoding="utf-8", newline="\n")

p = Path("latka_jazn/packaging/dependency_package_contract.py")
text = p.read_text(encoding="utf-8")
marker = "\nDEPENDENCY_ARTIFACT_NAME = \"JAZN_DEPENDENCY_ARTIFACT.json\""
if text.count(marker) != 1:
    raise SystemExit("dependency_package_contract.py: insertion marker mismatch")
text = text.replace(marker, "\n\ndef _mapping(value: Any) -> Mapping[str, Any]:\n    return value if isinstance(value, Mapping) else {}\n" + marker, 1)
for old, new in [
    ('actual_target = descriptor.get("target") if isinstance(descriptor.get("target"), dict) else {}', 'actual_target = _mapping(descriptor.get("target"))'),
    ('bundle_target = bundle_verify.get("target") if isinstance(bundle_verify.get("target"), dict) else {}', 'bundle_target = _mapping(bundle_verify.get("target"))'),
]:
    if text.count(old) != 1:
        raise SystemExit(f"dependency_package_contract.py: expected one match for {old!r}")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8", newline="\n")

replace_once("latka_jazn/tools/package_distribution.py", "from typing import Any, Sequence", "from typing import Any, Mapping, Sequence")
insert_once(
    "latka_jazn/tools/package_distribution.py",
    "from latka_jazn.version import PACKAGE_VERSION_FULL\n",
    "\n\ndef _mapping(value: Any) -> Mapping[str, Any]:\n    return value if isinstance(value, Mapping) else {}\n",
)
p = Path("latka_jazn/tools/package_distribution.py")
text = p.read_text(encoding="utf-8")
old = 'target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}'
if text.count(old) != 2:
    raise SystemExit(f"package_distribution.py: expected 2 target matches, got {text.count(old)}")
text = text.replace(old, 'target = _mapping(manifest.get("target"))')
old = 'descriptor = artifact.get("descriptor") if isinstance(artifact.get("descriptor"), dict) else {}'
if text.count(old) != 1:
    raise SystemExit("package_distribution.py: descriptor marker mismatch")
text = text.replace(old, 'descriptor = _mapping(artifact.get("descriptor"))', 1)
p.write_text(text, encoding="utf-8", newline="\n")
