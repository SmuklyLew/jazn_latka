"""Read-only resolution shared with the runtime; never load config into os.environ."""
from pathlib import Path
import os

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.core.system_config import read_system_config


def monitor_workspace(root: Path) -> Path:
    config = read_system_config(root)
    return workspace_runtime_path(root, os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR")
                                  or config.values.get("JAZN_RUNTIME_WORKSPACE_DIR"))
