from __future__ import annotations

"""Theme-aware modal dialogs for the canonical Memory Rebuild Studio."""

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from .themes import get_theme


class DialogBackend(Protocol):
    def choice(self, title: str, text: str, values: Sequence[tuple[Any, str]], *, default: Any = None) -> Any: ...
    def checklist(self, title: str, text: str, values: Sequence[tuple[str, str]], *, default_values: Sequence[str] = ()) -> list[str] | None: ...
    def input(self, title: str, text: str, default: str = "") -> str: ...
    def confirm(self, title: str, text: str) -> bool: ...
    def message(self, title: str, text: str) -> None: ...


def _dialog_style(theme_name: str):
    from prompt_toolkit.styles import Style

    theme = get_theme(theme_name)
    return Style.from_dict({
        "dialog": f"bg:{theme.panel} {theme.text}",
        "dialog frame.label": f"bg:{theme.panel} {theme.border} bold",
        "dialog.body": f"bg:{theme.panel_alt} {theme.text}",
        "dialog shadow": f"bg:{theme.background}",
        "button": f"bg:{theme.selection} {theme.text}",
        "button.focused": f"bg:{theme.accent} {theme.background} bold",
        "radio": theme.text,
        "radio-selected": f"{theme.accent_soft} bold",
        "checkbox": theme.text,
        "checkbox-selected": f"{theme.accent_soft} bold",
        "text-area": f"bg:{theme.background} {theme.text}",
    })


class PromptToolkitDialogs:
    def __init__(self, theme_name: Callable[[], str]):
        self._theme_name = theme_name

    @property
    def style(self):
        return _dialog_style(self._theme_name())

    def choice(self, title: str, text: str, values: Sequence[tuple[Any, str]], *, default: Any = None) -> Any:
        from prompt_toolkit.shortcuts import radiolist_dialog
        return radiolist_dialog(title=title, text=text, values=list(values), default=default, style=self.style).run()

    def checklist(self, title: str, text: str, values: Sequence[tuple[str, str]], *, default_values: Sequence[str] = ()) -> list[str] | None:
        from prompt_toolkit.shortcuts import checkboxlist_dialog
        selected = checkboxlist_dialog(title=title, text=text, values=list(values), default_values=list(default_values), style=self.style).run()
        if selected is None:
            return None
        return [str(value) for value in selected]

    def input(self, title: str, text: str, default: str = "") -> str:
        from prompt_toolkit.shortcuts import input_dialog
        value = input_dialog(title=title, text=text, default=default, style=self.style).run()
        return value if value is not None else ""

    def confirm(self, title: str, text: str) -> bool:
        from prompt_toolkit.shortcuts import yes_no_dialog
        return bool(yes_no_dialog(title=title, text=text, yes_text="Tak", no_text="Nie", style=self.style).run())

    def message(self, title: str, text: str) -> None:
        from prompt_toolkit.shortcuts import message_dialog
        message_dialog(title=title, text=text, ok_text="OK", style=self.style).run()


class TextDialogs:
    @staticmethod
    def _select(title: str, text: str, values: Sequence[tuple[Any, str]]) -> Any:
        print(f"\n=== {title} ===")
        if text:
            print(text)
        for index, (_value, label) in enumerate(values, 1):
            print(f"{index:>2}. {label}")
        raw = input("Wybór [Enter=powrót]: ").strip()
        if not raw:
            return None
        try:
            index = int(raw) - 1
        except ValueError:
            return None
        return values[index][0] if 0 <= index < len(values) else None

    def choice(self, title: str, text: str, values: Sequence[tuple[Any, str]], *, default: Any = None) -> Any:
        del default
        return self._select(title, text, values)

    def checklist(self, title: str, text: str, values: Sequence[tuple[str, str]], *, default_values: Sequence[str] = ()) -> list[str] | None:
        del default_values
        print(f"\n=== {title} ===")
        if text:
            print(text)
        for index, (_value, label) in enumerate(values, 1):
            print(f"{index:>2}. {label}")
        raw = input("Numery rozdzielone przecinkami; 'a'=wszystkie; Enter=anuluj: ").strip()
        if not raw:
            return None
        if raw.casefold() in {"a", "all", "wszystkie"}:
            return [value for value, _label in values]
        selected: list[str] = []
        for part in raw.split(","):
            try:
                index = int(part.strip()) - 1
            except ValueError:
                continue
            if 0 <= index < len(values):
                selected.append(values[index][0])
        return selected

    def input(self, title: str, text: str, default: str = "") -> str:
        print(f"\n=== {title} ===")
        raw = input(f"{text} [{default}]: ").strip()
        return raw or default

    def confirm(self, title: str, text: str) -> bool:
        print(f"\n=== {title} ===")
        return input(f"{text} [t/N]: ").strip().casefold() in {"t", "tak", "y", "yes"}

    def message(self, title: str, text: str) -> None:
        print(f"\n=== {title} ===\n{text}")


def make_dialogs(*, theme_name: Callable[[], str], text_ui: bool = False) -> DialogBackend:
    if text_ui:
        return TextDialogs()
    try:
        import prompt_toolkit  # noqa: F401
    except Exception:
        return TextDialogs()
    return PromptToolkitDialogs(theme_name)


__all__ = ["DialogBackend", "PromptToolkitDialogs", "TextDialogs", "make_dialogs"]