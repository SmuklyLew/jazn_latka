"""Operator navigation and commands over existing Window/Controller contracts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QBoxLayout, QDialog, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QStyle, QTabBar, QToolBar, QVBoxLayout,
)

from .core import STUDIOS

if TYPE_CHECKING:
    from .window import Window


class CommandPalette(QDialog):
    def __init__(self, host: Window, commands: list[QAction]):
        super().__init__(host)
        self.setWindowTitle("Wyszukiwarka poleceń")
        self.resize(620, 400)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Szukaj polecenia lub sekcji…")
        self.query.setAccessibleName("Filtr poleceń")
        self.results = QListWidget()
        self.results.setAccessibleName("Dostępne polecenia")
        layout.addWidget(self.query)
        layout.addWidget(self.results)
        self.commands = commands
        self.query.textChanged.connect(self.filter)
        self.query.returnPressed.connect(self.execute)
        self.results.itemActivated.connect(lambda _item: self.execute())
        self.query.installEventFilter(self)
        self.filter("")

    def filter(self, text: str) -> None:
        self.results.clear()
        for index, command in enumerate(self.commands):
            if text.casefold() in command.text().casefold():
                item = QListWidgetItem(command.text().replace("&", ""))
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(command.toolTip() or command.text())
                self.results.addItem(item)
        self.results.setCurrentRow(0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.query and event.type() == QEvent.Type.KeyPress:
            from PySide6.QtGui import QKeyEvent
            if isinstance(event, QKeyEvent) and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                delta = 1 if event.key() == Qt.Key.Key_Down else -1
                self.results.setCurrentRow(max(0, min(self.results.count() - 1, self.results.currentRow() + delta)))
                return True
        return super().eventFilter(watched, event)

    def execute(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        action = self.commands[item.data(Qt.ItemDataRole.UserRole)]
        self.accept()
        action.trigger()


class WorkbenchShell(QObject):
    def __init__(self, host: Window):
        super().__init__(host)
        self.host = host
        self.commands: list[QAction] = []
        self.palette_dialog: CommandPalette | None = None
        self.compact_sidebar: bool | None = None
        self.menus = {name: host.menuBar().addMenu(name) for name in
                      ("Plik", "Edycja", "Widok", "Terminal", "Usługi", "Jaźń", "Studia", "TPA", "Narzędzia", "Pomoc")}
        self.command("Plik", "Kreator konfiguracji…", host.open_setup)
        self.command("Plik", "Zapisz ustawienia Studio", host.save, "Ctrl+S")
        self.command("Plik", "Eksportuj raport diagnostyczny…", host.export)
        self.command("Plik", "Zamknij Studio", host.close, "Alt+F4")
        for label, method, shortcut in (("Cofnij", "undo", "Ctrl+Z"), ("Ponów", "redo", "Ctrl+Y"),
                                        ("Wytnij", "cut", "Ctrl+X"), ("Kopiuj", "copy", "Ctrl+C"),
                                        ("Wklej", "paste", "Ctrl+V"), ("Zaznacz wszystko", "selectAll", "Ctrl+A")):
            # Editors own their normal shortcuts, preserving native Qt behavior.
            self.command("Edycja", label, lambda key=method: self.edit(key))
        self.command("Widok", "Wyszukaj polecenie…", self.open_palette, "Ctrl+Shift+P")
        self.command("Widok", "Nawigacja", host.toggle_sidebar)
        self.command("Widok", "Nawigacja po lewej / prawej", host.switch_sidebar)
        self.command("Widok", "Przywróć bezpieczny układ", host.reset_layout)
        from .workbench_theme import WORKBENCH_PROFILES
        for profile in WORKBENCH_PROFILES:
            self.command("Widok", "Styl JSS: " + profile.label,
                         lambda key=profile.key: host.select_style(key))
        self.command("Widok", "Stany serwera / Runtime / MCP / Ollama…", host.open_service_status)
        self.command("Widok", "Problemy", lambda: host.workspace.show(0))
        self.command("Widok", "Output / Logi", lambda: host.workspace.show(1))
        self.command("Widok", "Ostatni panel narzędzi", lambda: host.workspace.show(
            host.workspace.tabs.currentIndex()), "F12")
        self.command("Widok", "Ukryj panel narzędzi", host.workspace.dock.hide, "Shift+Esc")
        self.command("Widok", "Historia TPA i zadań", lambda: host.workspace.show(3))
        self.command("Widok", "Dane techniczne", lambda: host.workspace.show(4))
        self.command("Terminal", "Konsole zadań w dolnym panelu", lambda: host.workspace.show(2))
        self.command("Terminal", "Interaktywny lokalny PTY", lambda: host.workspace.show(5))
        self.command("Terminal", "Otwórz PowerShell w osobnym oknie", host.workspace.open_system_terminal)
        self.command("Terminal", "Otwórz lokalny czat Jaźni (run.py)", host.workspace.open_tty)
        self.command("Terminal", "Obsługa PTY / ConPTY", lambda: QMessageBox.information(
            host, "Terminal", "Konsole zadań nie emulują terminala TTY. PowerShell uruchamia się w osobnym oknie. Wbudowany ConPTY/PTY wymaga osobnej implementacji oraz testów na Windows i Linux."))
        self.command("Usługi", "Panel usług", lambda: host.navigate("Usługi i procesy"))
        self.command("Usługi", "Sprawdź wszystkie usługi", host.refresh_services)
        for operation, label in (("start", "Start wybranej usługi"), ("stop", "Stop wybranej usługi"), ("restart", "Restart wybranej usługi")):
            self.command("Usługi", label, lambda op=operation: host.selected_service_action(op))
        self.command("Jaźń", "Czat lokalny", lambda: host.navigate("Czat lokalny"))
        self.command("Jaźń", "Połączenie z ChatGPT", lambda: host.navigate("Połączenie z ChatGPT"))
        self.command("Jaźń", "Dowody MEMORY", lambda: host.navigate("Dowody MEMORY"))
        targets = {"operator": "Developer", "start": "Usługi i procesy", "configuration": "Konfiguracja Qt",
                   "version": "Wersje Qt", "memory": "Dowody MEMORY", "tests": "Katalog testów"}
        for studio in STUDIOS:
            self.command("Studia", studio.label, lambda key=studio.key: self.studio(key, targets))
        for label in ("Import/Export rozmów — formularze MEMORY", "Restore MEMORY — dostępność"):
            self.command("Studia", label, lambda: QMessageBox.information(host, "Migracja Studio",
                "Pełny natywny workflow importu/restore pozostaje w P4. Klasyczne narzędzia są zachowane; operacje wymagają planu i izolowanego projektu."))
        self.command("TPA", "Otwórz TPA — 22 scenariusze", lambda: host.navigate("TPA"))
        self.command("TPA", "Sprawdź gotowość TPA", lambda: host.local_acceptance_panel.check_ready())
        self.command("Narzędzia", "Ustawienia", lambda: host.navigate("Ustawienia"), "Ctrl+,")
        self.command("Narzędzia", "Diagnostyka", lambda: host.navigate("Diagnostyka"))
        self.command("Narzędzia", "Developer", lambda: host.navigate("Developer"))
        self.command("Pomoc", "O programie i licencje", lambda: host.navigate("O programie"))
        self.command("Pomoc", "Wyszukaj polecenie…", self.open_palette)
        self.section_tabs = QTabBar()
        self.section_tabs.setObjectName("heartSectionTabs")
        self.section_tabs.setAccessibleName("Otwarte sekcje Studio")
        self.section_tabs.setExpanding(False)
        self.section_tabs.setUsesScrollButtons(True)
        canvas = host.topbar.parentWidget()
        layout = canvas.layout() if canvas is not None else None
        if isinstance(layout, QBoxLayout):
            layout.insertWidget(1, self.section_tabs)
        self.section_tabs.currentChanged.connect(self.select_tab)
        host.nav.currentRowChanged.connect(self.sync_section)
        self.activity = QToolBar("Aktywność", host)
        self.activity.setObjectName("heartActivityBar")
        self.activity.setMovable(False)
        self.activity.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        for title, icon in (("Pulpit", QStyle.StandardPixmap.SP_ComputerIcon),
                            ("Czat lokalny", QStyle.StandardPixmap.SP_MessageBoxInformation),
                            ("Usługi i procesy", QStyle.StandardPixmap.SP_DriveNetIcon),
                            ("Dowody MEMORY", QStyle.StandardPixmap.SP_DirHomeIcon),
                            ("Katalog testów", QStyle.StandardPixmap.SP_FileDialogListView),
                            ("TPA", QStyle.StandardPixmap.SP_DialogApplyButton),
                            ("Developer", QStyle.StandardPixmap.SP_DirIcon),
                            ("Ustawienia", QStyle.StandardPixmap.SP_FileDialogDetailedView)):
            action = self.activity.addAction(host.style().standardIcon(icon), title)
            action.setToolTip(title)
            action.triggered.connect(lambda _checked=False, target=title: host.navigate(target))
        host.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.activity)
        host.installEventFilter(self)
        self.sync_section(host.nav.currentRow())

    def command(self, menu: str, label: str, callback: Callable, shortcut: str = "") -> None:
        action = self.menus[menu].addAction(label)
        action.setToolTip(menu + " / " + label)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: self.host.guard(callback))
        self.commands.append(action)

    def open_palette(self) -> None:
        self.palette_dialog = CommandPalette(self.host, self.commands)
        self.palette_dialog.show()
        self.palette_dialog.query.setFocus()

    def edit(self, method: str) -> None:
        widget = self.host.focusWidget()
        callback = getattr(widget, method, None)
        if callable(callback):
            callback()
        else:
            self.host.statusBar().showMessage("Pole z fokusem nie obsługuje tej operacji edycji.", 5000)

    def studio(self, key: str, targets: dict[str, str]) -> None:
        self.host.navigate(targets.get(key, "Studia Jaźni"))
        index = self.host.studio_choice.findData(key)
        if key not in targets and index >= 0:
            self.host.studio_choice.setCurrentIndex(index)
            self.host.load_studio_operations()

    def sync_section(self, row: int) -> None:
        item = self.host.nav.item(row)
        if item is None:
            return
        title = item.text()
        index = next((i for i in range(self.section_tabs.count()) if self.section_tabs.tabText(i) == title), -1)
        if index < 0:
            index = self.section_tabs.addTab(title)
        self.section_tabs.setCurrentIndex(index)

    def select_tab(self, index: int) -> None:
        if index >= 0:
            self.host.navigate(self.section_tabs.tabText(index))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.host and event.type() == QEvent.Type.Resize:
            compact = self.host.width() < 1050
            if compact and self.compact_sidebar is None:
                self.compact_sidebar = not self.host.sidebar.isHidden()
                self.host.sidebar.hide()
            elif not compact and self.compact_sidebar is not None:
                self.host.sidebar.setVisible(self.compact_sidebar)
                self.compact_sidebar = None
            self.activity.setVisible(not compact)
            self.section_tabs.setVisible(not compact)
            self.host.workbench_status.setVisible(not compact)
        return False
