"""Native Qt Configuration Studio, backed by the original guarded profile engine.

All reads/validation/preview/save/restore run in the separate canonical
studio_worker interpreter. This GUI never writes a profile or touches daemon
settings directly. A completed subprocess is not proof of daemon readiness.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .core import Controller, StudioError


def profile_fingerprint(values: dict[str, str], digest: str | None) -> str:
    """Bind a reviewed draft to its exact on-disk version."""
    payload = json.dumps({"values": values, "digest": digest},
                         sort_keys=True, ensure_ascii=False).encode("utf-8")
    return sha256(payload).hexdigest()


def launch_command(root: Path, profile_path: str) -> str:
    """Display the original explicit Windows launcher, never run it."""
    launcher = root / "tools" / "windows" / "Start-JaznWithConfig.ps1"
    if (not Path(profile_path).is_absolute() or any(ch in profile_path for ch in ('"', "\n", "\r"))):
        raise ValueError("Brak zweryfikowanej ścieżki profilu.")
    return f'pwsh -File "{launcher}" -Profile "{profile_path}"'


class ConfigurationPanel(QWidget):
    """Unsaved-draft and CAS-aware panel; legacy Tk app stays available."""

    def __init__(self, core: Controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.core = core
        self.digest: str | None = None
        self.loaded: dict[str, str] = {}
        self.profile_path = ""
        self.widgets: dict[str, QLineEdit | QComboBox] = {}
        self.preview_hash = ""
        self.requested_preview_hash = ""
        self.busy = ""
        self.loaded_once = False
        main = QVBoxLayout(self)
        self.notice = QLabel(
            "Profil dotyczy wyłącznie przyszłych uruchomień. "
            "Nie zmienia ustawień działającego daemona ani prywatnej MEMORY."
        )
        self.notice.setWordWrap(True)
        main.addWidget(self.notice)
        self.status = QLabel("Nie wczytano profilu. Wybierz „Wczytaj profil”.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Status natywnego Studia Konfiguracji")
        main.addWidget(self.status)

        buttons = QHBoxLayout()
        self.load_button = QPushButton("Wczytaj profil")
        self.load_button.clicked.connect(self.reload)
        buttons.addWidget(self.load_button)
        self.paths_button = QPushButton("Mapa ścieżek (odczyt)")
        self.paths_button.clicked.connect(lambda: self._run("profile-paths"))
        buttons.addWidget(self.paths_button)
        main.addLayout(buttons)

        self.form = QFormLayout()
        main.addLayout(self.form)
        self.check_button = QPushButton("Sprawdź wartości")
        self.check_button.clicked.connect(self.validate)
        self.preview_button = QPushButton("Podgląd zmian — bez zapisu")
        self.preview_button.clicked.connect(self.preview)
        self.save_button = QPushButton("Zapisz po zatwierdzeniu")
        self.save_button.clicked.connect(self.save)
        self.restore_button = QPushButton("Przywróć poprzedni profil")
        self.restore_button.clicked.connect(self.restore)
        self.copy_button = QPushButton("Kopiuj komendę startową")
        self.copy_button.clicked.connect(self.copy_command)
        for widget in (self.check_button, self.preview_button, self.save_button,
                       self.restore_button, self.copy_button):
            main.addWidget(widget)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Odczytowa mapa ścieżek lub podgląd profilu")
        self.details.setMaximumBlockCount(400)
        self.details.setMinimumHeight(150)
        main.addWidget(self.details)
        main.addStretch(1)
        self._enabled(False)

    def _enabled(self, ready: bool) -> None:
        for button in (self.check_button, self.preview_button, self.restore_button, self.copy_button):
            button.setEnabled(ready and not self.busy)
        self.save_button.setEnabled(ready and not self.busy and
                                    bool(self.preview_hash) and self.dirty)
        self.load_button.setEnabled(not self.busy)
        self.paths_button.setEnabled(not self.busy)

    def values(self) -> dict[str, str]:
        return {
            key: widget.currentText() if isinstance(widget, QComboBox) else widget.text()
            for key, widget in self.widgets.items()
        }

    @property
    def dirty(self) -> bool:
        return self.loaded_once and self.values() != {
            key: self.loaded.get(key, "") for key in self.widgets
        }

    def _changed(self, *_: object) -> None:
        self.preview_hash = ""
        if self.loaded_once and not self.busy:
            self.status.setText(
                "Zmiany niezapisane — zweryfikuj projekt i obejrzyj podgląd przed zapisem."
                if self.dirty else "Profil bez niezapisanych zmian."
            )
        self._enabled(self.loaded_once)

    def may_discard(self) -> bool:
        if not self.dirty:
            return True
        return (QMessageBox.question(
            self, "Niezapisane zmiany",
            "Odrzucić niezapisane wartości profilu przyszłych uruchomień?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes)

    def _run(self, operation: str, data: dict[str, Any] | None = None) -> None:
        if self.busy:
            raise StudioError("Inna operacja Konfiguracji jest jeszcze wykonywana.")
        self.busy = operation
        if operation == "profile-preview" and data is not None:
            self.requested_preview_hash = profile_fingerprint(data["values"], data.get("digest"))
        self._enabled(self.loaded_once)
        try:
            self.core.studio_helper(operation, data=data)
        except (StudioError, OSError, ValueError):
            self.busy = ""
            self._enabled(self.loaded_once)
            raise
        self.status.setText("Trwa operacja " + operation + " — oczekuję na wynik.")

    def reload(self) -> None:
        if self.may_discard():
            self._run("profile-read")

    def validate(self) -> None:
        if self.loaded_once:
            self._run("profile-validate", {"values": self.values()})

    def preview(self) -> None:
        if self.loaded_once:
            self._run("profile-preview", {"values": self.values(), "digest": self.digest})

    def save(self) -> None:
        if not self.loaded_once or not self.dirty:
            return
        values = self.values()
        if self.preview_hash != profile_fingerprint(values, self.digest):
            self.status.setText("Podgląd jest nieaktualny — ponownie sprawdź zmiany.")
            self.preview_hash = ""
            self._enabled(True)
            return
        if QMessageBox.question(
            self, "Zapis profilu",
            "Zapisać wyłącznie profil przyszłych uruchomień? Aktywny daemon nie zostanie zmieniony.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._run("profile-save", {"values": values, "digest": self.digest})

    def restore(self) -> None:
        if not self.loaded_once or not self.may_discard():
            return
        if QMessageBox.question(
            self, "Przywrócenie profilu",
            "Nadpisać zapisany profil jego kopią poprzednią? To operacja zapisu z kontrolą wersji.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._run("profile-restore", {"digest": self.digest})

    def copy_command(self) -> None:
        command = launch_command(self.core.root, self.profile_path)
        clipboard = QApplication.clipboard()
        clipboard.setText(command)
        self.status.setText("Skopiowano przykładową komendę. Nie uruchomiono procesu.")

    def choose_path(self, key: str, kind: str) -> None:
        widget = self.widgets.get(key)
        if not isinstance(widget, QLineEdit) or kind == "memory_database":
            return  # database is relative to MEMORY; no absolute file picker
        current = widget.text().strip()
        if kind == "directory":
            chosen = QFileDialog.getExistingDirectory(self, "Katalog", current)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "Plik", current)
        if chosen:
            widget.setText(chosen)

    def receive(self, key: str, value: object) -> None:
        if not isinstance(value, dict):
            return
        mode = key.removeprefix("helper:").removesuffix(":")
        if mode != self.busy:
            return
        if mode in {"profile-read", "profile-save", "profile-restore"}:
            if value.get("schema") != "jazn_config_snapshot/v1":
                self._failed("Niepoprawny kontrakt odpowiedzi profilu.")
                return
            self._snapshot(value)
            self.status.setText(
                "Wczytano profil przyszłych uruchomień."
                if mode == "profile-read" else "Zapis profilu potwierdzony i ponownie odczytany."
            )
        elif mode == "profile-preview":
            if value.get("schema") != "jazn_config_profile_preview/v1" or value.get("read_only") is not True:
                self._failed("Brak wiarygodnego podglądu dry-run.")
                return
            if value.get("profile_sha256") != self.digest:
                self._failed("Profil zmieniono — wymagane ponowne wczytanie.")
                return
            if value.get("location_change_requires_runtime_verification"):
                self._failed("Marker runtime: zmiana lokalizacji wymaga osobnej weryfikacji.")
                return
            lines = [f'Zmienionych ustawień: {value.get("changes_count")}']
            for item in value.get("rows", []):
                if isinstance(item, dict) and item.get("changed") is True:
                    lines.append(str(item.get("title")) + " (" + str(item.get("key")) + ")")
                    lines.append("  zapisane: " + str(item.get("saved")))
                    lines.append("  projekt:  " + str(item.get("proposed")))
            self.details.setPlainText("\n".join(lines))
            if (value.get("changes_count") and
                    self.requested_preview_hash == profile_fingerprint(self.values(), self.digest) and
                    set(value.get("changed_keys", [])) == set(
                k for k in self.widgets if self.loaded.get(k) != self.values().get(k)
            )):
                self.preview_hash = profile_fingerprint(self.values(), self.digest)
            self.status.setText("Podgląd odczytowy zatwierdzony do ręcznej decyzji.")
        elif mode == "profile-paths":
            if value.get("schema") != "jazn_config_path_map/v1" or value.get("read_only") is not True:
                self._failed("Błędna mapa ścieżek.")
                return
            rows = value.get("rows", [])
            self.details.setPlainText("\n".join(
                str(x.get("name")) + " | " + str(x.get("path")) +
                " | istnieje: " + str(x.get("exists")) + " | " + str(x.get("note"))
                for x in rows if isinstance(x, dict)
            ))
            self.status.setText("Mapa ścieżek odczytana — nie jest dowodem aktywności daemona.")
        elif mode == "profile-validate":
            if value.get("schema") != "jazn_config_validation/v1" or value.get("saved") is not False:
                self._failed("Niepoprawny wynik walidacji.")
                return
            self.status.setText("Poprawny profil: " + str(value.get("count")) +
                                " nadpisań. Żadnych zmian nie zapisano.")
        self.busy = ""
        self.requested_preview_hash = ""
        self._enabled(self.loaded_once)

    def _snapshot(self, value: dict[str, Any]) -> None:
        entries = value.get("values")
        fields = value.get("fields")
        if not isinstance(entries, dict) or not isinstance(fields, list):
            self._failed("Niepoprawna zawartość profilu.")
            return
        while self.form.rowCount():
            self.form.removeRow(0)
        self.widgets.clear()
        self.loaded = {str(k): str(v) for k, v in entries.items()}
        self.profile_path = str(value.get("profile_path") or "")
        self.digest = value.get("digest") if isinstance(value.get("digest"), str) else None
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("key"), str):
                continue
            key = field["key"]
            choices = field.get("choices")
            if isinstance(choices, list) and choices:
                widget: QLineEdit | QComboBox = QComboBox()
                widget.addItems([""] + [str(x) for x in choices])
                widget.setCurrentText(self.loaded.get(key, ""))
                widget.currentTextChanged.connect(self._changed)
            else:
                widget = QLineEdit(self.loaded.get(key, ""))
                widget.textChanged.connect(self._changed)
            widget.setAccessibleName(str(field.get("title", key)))
            widget.setToolTip(str(field.get("hint", "")))
            self.widgets[key] = widget
            self.form.addRow(str(field.get("title", key)), widget)
            if isinstance(widget, QLineEdit) and field.get("kind") in {"directory", "file"}:
                browse = QPushButton("…")
                browse.setAccessibleName("Wybierz ścieżkę dla " + key)
                browse.clicked.connect(
                    lambda _=False, k=key, kind=str(field["kind"]): self.choose_path(k, kind)
                )
                self.form.addRow("", browse)
        self.loaded_once = True
        self.preview_hash = ""

    def _failed(self, reason: str) -> None:
        self.preview_hash = ""
        self.requested_preview_hash = ""
        self.status.setText("BŁĄD Konfiguracji: " + reason)
        self.busy = ""
        self._enabled(self.loaded_once)

    def receive_state(self, key: str, value: object) -> None:
        mode = key.removeprefix("helper:").removesuffix(":")
        if mode != self.busy or not isinstance(value, dict):
            return
        if value.get("state") in {"failed", "stopped"}:
            self._failed("Operacja nie została zakończona: " + str(value.get("error") or "nieznana"))
