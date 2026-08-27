from __future__ import annotations

"""Full-screen layout composition for Memory Rebuild Studio P0.

The module is intentionally presentation-only.  Page state and actions live in
``studio_p0.py``; colour tokens live in ``theme.py`` / ``themes.py``.
"""

from typing import Any, Protocol


class StudioLayoutState(Protocol):
    def header_fragments(self) -> Any: ...
    def tab_fragments(self) -> Any: ...
    def sidebar_fragments(self) -> Any: ...
    def content_fragments(self) -> Any: ...
    def status_fragments(self) -> Any: ...
    def footer_fragments(self) -> Any: ...


def build_studio_layout(state: StudioLayoutState):
    """Return a prompt_toolkit ``Layout`` for the current studio state."""

    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, VSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.widgets import Frame

    header = Window(
        FormattedTextControl(state.header_fragments, focusable=False),
        height=2,
        style="class:header",
    )
    tabs = Window(
        FormattedTextControl(state.tab_fragments, focusable=False),
        height=1,
        style="class:tabs",
    )
    sidebar_body = Window(
        FormattedTextControl(state.sidebar_fragments, focusable=False),
        width=Dimension(min=25, preferred=31, max=38),
        wrap_lines=False,
        style="class:sidebar",
    )
    content_body = Window(
        FormattedTextControl(state.content_fragments, focusable=False),
        wrap_lines=True,
        style="class:content",
    )
    body = VSplit(
        [
            Frame(sidebar_body, title=" Nawigacja ", style="class:frame"),
            Frame(content_body, title=" Szczegóły ", style="class:frame"),
        ],
        padding=1,
        padding_char="│",
        padding_style="class:muted",
    )
    status = Window(
        FormattedTextControl(state.status_fragments, focusable=False),
        height=1,
        style="class:status",
    )
    footer = Window(
        FormattedTextControl(state.footer_fragments, focusable=False),
        height=1,
        style="class:footer",
    )
    return Layout(HSplit([header, tabs, body, status, footer]))


__all__ = ["StudioLayoutState", "build_studio_layout"]
