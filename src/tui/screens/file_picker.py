"""
Enhancify File Picker Screen
Touch and keyboard friendly file browser for importing APKs, bundles, and JSON files from storage.
"""

from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.theme import palette
from src.tui.screens.base import BaseScreen
from src.tui.widgets.button_bar import ButtonBar
from src.utils import format_size


ALLOWED_EXTENSIONS = {".apk", ".apkm", ".xapk", ".apks", ".json"}


class FilePickerScreen(BaseScreen[Optional[Path]]):
    """File browser screen."""

    BINDINGS = [
        ("u", "up", "Up Directory"),
        ("b", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, start_dir: Optional[Path] = None, allowed_exts: Optional[set] = None, **kwargs):
        super().__init__(**kwargs)
        # Determine valid start directory
        storage_shared = Path.home() / "storage" / "shared"
        sdcard = Path("/sdcard")

        if start_dir and start_dir.exists():
            self.current_dir = start_dir
        elif storage_shared.exists():
            self.current_dir = storage_shared
        elif sdcard.exists():
            self.current_dir = sdcard
        else:
            self.current_dir = Path.home()

        self.allowed_exts = allowed_exts or ALLOWED_EXTENSIONS

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="card list-card"):
            yield Label("📂 Select File from Storage", classes="card-title")
            yield Label(f"Current Path: [bold $enh-accent-2]{self.current_dir}[/]", id="path-label", classes="card-desc")

            with ButtonBar():
                yield Button("⬆️ Up Directory [U]", id="btn-up")
                yield Button("❌ Cancel [B]", id="btn-cancel", classes="btn-secondary")

            yield ListView(id="file-list")

    def on_mount(self) -> None:
        self.populate_directory()

    def populate_directory(self) -> None:
        """Populate ListView with entries from current_dir."""
        try:
            self.query_one("#path-label", Label).update(f"Current Path: [bold $enh-accent-2]{self.current_dir}[/]")
        except Exception:
            pass

        file_list = self.query_one("#file-list", ListView)
        file_list.clear()

        try:
            entries = sorted(list(self.current_dir.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            file_list.append(ListItem(Label(Text("❌ Permission denied or directory unreadable", style=palette()["danger"]))))
            return

        pal = palette()
        for p in entries:
            if p.name.startswith("."):
                continue

            if p.is_dir():
                txt = Text()
                txt.append("📁 ", style=f"bold {pal['accent_2']}")
                txt.append(f"{p.name}/", style=f"bold {pal['text']}")
                item = ListItem(Label(txt))
                item.entry_is_dir = True
                item.dir_name = p.name
                file_list.append(item)
            elif p.suffix.lower() in self.allowed_exts:
                txt = Text()
                txt.append("📦 ", style=f"bold {pal['accent']}")
                txt.append(f"{p.name:<30}", style=pal["text"])
                try:
                    sz_str = format_size(p.stat().st_size)
                    txt.append(f" ({sz_str})", style=pal["muted"])
                except Exception:
                    pass
                item = ListItem(Label(txt))
                item.entry_is_dir = False
                item.file_path = p
                file_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if getattr(event.item, "entry_is_dir", False):
            dir_name = event.item.dir_name
            next_dir = self.current_dir / dir_name
            if next_dir.is_dir():
                self.current_dir = next_dir
                self.populate_directory()
        elif hasattr(event.item, "file_path"):
            self.dismiss(event.item.file_path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-up":
            self.action_up()
        elif btn_id == "btn-cancel":
            self.action_cancel()

    def action_up(self) -> None:
        if self.current_dir.parent != self.current_dir:
            self.current_dir = self.current_dir.parent
            self.populate_directory()

    def action_cancel(self) -> None:
        self.dismiss(None)
