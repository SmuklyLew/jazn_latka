from __future__ import annotations

"""v16 release-metadata compatibility adapter.

v16 deliberately uses ``PACKAGE_VERSION = "16.0.0"`` without forcing the old
presentation prefix ``v``. The underlying deterministic release implementation
is retained unchanged; only its package-version validator is widened to accept
both historical ``v15...`` values and canonical unprefixed semantic versions.
"""

import re
from collections.abc import Iterable

from latka_jazn.tools import _release_metadata_sync_impl as _impl

_impl._PACKAGE_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)+$")

from latka_jazn.tools._release_metadata_sync_impl import *  # noqa: F401,F403,E402


def main(argv: Iterable[str] | None = None) -> int:
    """Run the implementation while preserving monkeypatchable public hooks.

    Tests and downstream callers historically monkeypatch functions on this public
    module. Keep that contract intact even though v16 uses a compatibility adapter.
    """

    _impl.check_release_metadata = check_release_metadata
    _impl.write_release_metadata = write_release_metadata
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
