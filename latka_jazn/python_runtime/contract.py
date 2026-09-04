from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import os
import platform
import re
import sys

from latka_jazn.dependencies.common import current_libc_family, current_platform_alias

RUNTIME_MANIFEST_SCHEMA = "jazn_python_runtime_manifest/v1"
RUNTIME_SET_SCHEMA = "jazn_python_runtime_set/v1"
RUNTIME_MANIFEST_NAME = "JAZN_PYTHON_RUNTIME_MANIFEST.json"
RUNTIME_SET_NAME = "JAZN_PYTHON_RUNTIME_SET.json"
RUNTIME_INDEX_NAME = "JAZN_PYTHON_RUNTIME_INDEX.tsv"
DEFAULT_PYTHON_PREFERENCE = ("3.14", "3.13", "3.12")
SUPPORTED_PLATFORM_ALIASES = frozenset(
    {"windows-x64", "windows-arm64", "linux-x64", "linux-arm64", "macos-x64", "macos-arm64"}
)
_ARCH = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}
_PYTHON_MINOR_RE = re.compile(r"^\d+\.\d+$")


class PythonRuntimeContractError(ValueError):
    """Fail-closed Python runtime bundle/target contract error."""


@dataclass(frozen=True, slots=True)
class HostTarget:
    alias: str
    architecture: str
    libc_family: str
    os_family: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeTarget:
    alias: str
    python_version: str
    implementation: str
    abi: str
    architecture: str
    libc_family: str

    @property
    def target_id(self) -> str:
        libc = f"-{self.libc_family}" if self.alias.startswith("linux-") else ""
        return f"{self.alias}{libc}-py{self.python_version.replace('.', '')}"

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["target_id"] = self.target_id
        return payload


def normalize_python_minor(value: str) -> str:
    raw = str(value or "").strip()
    if not _PYTHON_MINOR_RE.fullmatch(raw):
        raise PythonRuntimeContractError(f"invalid_python_minor:{value!r}")
    major, minor = (int(part) for part in raw.split(".", 1))
    if major != 3 or minor < 12:
        raise PythonRuntimeContractError(f"unsupported_python_minor:{raw}")
    return f"{major}.{minor}"


def normalize_target_alias(value: str) -> str:
    alias = str(value or "").strip().lower()
    if alias not in SUPPORTED_PLATFORM_ALIASES:
        raise PythonRuntimeContractError(f"unsupported_runtime_target_alias:{value!r}")
    return alias


def _architecture_for_alias(alias: str) -> str:
    if alias.endswith("-x64"):
        return "x86_64"
    if alias.endswith("-arm64"):
        return "arm64"
    raise PythonRuntimeContractError(f"unsupported_runtime_architecture:{alias}")


def runtime_target(
    alias: str,
    python_version: str,
    *,
    libc_family: str | None = None,
    implementation: str = "cp",
    abi: str | None = None,
) -> RuntimeTarget:
    normalized_alias = normalize_target_alias(alias)
    py = normalize_python_minor(python_version)
    impl = str(implementation or "").strip().lower()
    if impl != "cp":
        raise PythonRuntimeContractError(f"unsupported_runtime_implementation:{implementation!r}")
    expected_abi = f"cp{py.replace('.', '')}"
    normalized_abi = str(abi or expected_abi).strip().lower()
    if normalized_abi != expected_abi:
        raise PythonRuntimeContractError(
            f"runtime_abi_python_mismatch:{normalized_abi!r}!={expected_abi!r}"
        )
    if normalized_alias.startswith("linux-"):
        libc = str(libc_family or "").strip().lower()
        if libc not in {"glibc", "musl"}:
            raise PythonRuntimeContractError(
                f"linux_runtime_requires_explicit_glibc_or_musl:{libc_family!r}"
            )
    else:
        libc = "not-applicable"
    return RuntimeTarget(
        alias=normalized_alias,
        python_version=py,
        implementation=impl,
        abi=normalized_abi,
        architecture=_architecture_for_alias(normalized_alias),
        libc_family=libc,
    )


def runtime_target_from_mapping(value: object) -> RuntimeTarget:
    """Parse an untrusted JSON-like target object with a fail-closed type boundary."""

    if not isinstance(value, Mapping):
        raise PythonRuntimeContractError(
            f"runtime_target_not_mapping:{type(value).__name__}"
        )
    mapping: Mapping[object, object] = value
    return runtime_target(
        str(mapping.get("alias") or ""),
        str(mapping.get("python_version") or ""),
        libc_family=str(mapping.get("libc_family") or ""),
        implementation=str(mapping.get("implementation") or "cp"),
        abi=str(mapping.get("abi") or ""),
    )


def detect_host_target() -> HostTarget:
    alias = current_platform_alias()
    if alias not in SUPPORTED_PLATFORM_ALIASES:
        raise PythonRuntimeContractError(f"unsupported_host_target:{alias}")
    machine = platform.machine().lower()
    architecture = _ARCH.get(machine) or machine or "unknown"
    libc = current_libc_family() if alias.startswith("linux-") else "not-applicable"
    if alias.startswith("linux-") and libc not in {"glibc", "musl"}:
        raise PythonRuntimeContractError(f"unknown_linux_libc_family:{libc}")
    return HostTarget(
        alias=alias,
        architecture=architecture,
        libc_family=libc,
        os_family=alias.split("-", 1)[0],
    )


def target_matches_host(target: RuntimeTarget, host: HostTarget) -> bool:
    if target.alias != host.alias or target.architecture != host.architecture:
        return False
    if target.alias.startswith("linux-"):
        return target.libc_family == host.libc_family
    return True


def python_preference(
    requested: str | None = None,
    preference: Sequence[str] = DEFAULT_PYTHON_PREFERENCE,
) -> tuple[str, ...]:
    explicit = str(requested or os.environ.get("JAZN_PYTHON_VERSION") or "").strip()
    if explicit:
        return (normalize_python_minor(explicit),)
    normalized: list[str] = []
    for item in preference:
        version = normalize_python_minor(str(item))
        if version not in normalized:
            normalized.append(version)
    return tuple(normalized)


def current_interpreter_target() -> RuntimeTarget:
    alias = current_platform_alias()
    libc = current_libc_family() if alias.startswith("linux-") else "not-applicable"
    implementation = "cp" if sys.implementation.name == "cpython" else sys.implementation.name[:2]
    return runtime_target(
        alias,
        f"{sys.version_info.major}.{sys.version_info.minor}",
        libc_family=libc,
        implementation=implementation,
    )
