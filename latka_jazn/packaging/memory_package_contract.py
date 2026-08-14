"""Public facade for the independent system/memory package lifecycle."""
from .memory_package_attach import _infer_memory_base_zip_name, attach_memory_package
from .memory_package_manifest import verify_memory_package_manifest
from .memory_package_types import (
    MEMORY_ATTACH_MARKER_PATH,
    MEMORY_FORMAT_VERSION,
    MEMORY_MANIFEST_SCHEMA_V1,
    MEMORY_MANIFEST_SCHEMA_V2,
    MEMORY_PACKAGE_MANIFEST_PATH,
    MEMORY_RUNTIME_COMPATIBILITY_CONTRACT,
    MemoryAttachResult,
    inspect_sqlite_memory_file,
)

__all__ = [
    "MEMORY_ATTACH_MARKER_PATH", "MEMORY_FORMAT_VERSION", "MEMORY_MANIFEST_SCHEMA_V1",
    "MEMORY_MANIFEST_SCHEMA_V2", "MEMORY_PACKAGE_MANIFEST_PATH",
    "MEMORY_RUNTIME_COMPATIBILITY_CONTRACT", "MemoryAttachResult", "attach_memory_package",
    "inspect_sqlite_memory_file", "verify_memory_package_manifest",
]
