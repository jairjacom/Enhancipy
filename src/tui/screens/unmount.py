"""
Enhancify Root Unmount Screen
Allows unmounting active Magisk / KernelSU / APatch bind mounts for patched apps.
"""

import subprocess
from typing import List

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.environment import env
from src.tui.screens.base import BaseScreen
from src.tui.widgets.dialogs import ConfirmDialog, MessageDialog
from src.tui.widgets.button_bar import ButtonBar
from src.theme import palette
from src.utils import run_command


class UnmountScreen(BaseScreen):
    """Root mode unmount manager screen."""

    BINDINGS = [
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="card list-card"):
            yield Label("🔒 Unmount Root Patched Application", classes="card-title")
            yield Label("Select an active mounted application to unmount and remove boot scripts:", classes="card-desc")

            with ButtonBar():
                yield Button("🔙 Back [B]", id="btn-back", classes="btn-secondary")

            yield ListView(id="mounted-list")

    def on_mount(self) -> None:
        self.populate_mounted()

    def populate_mounted(self) -> None:
        m_list = self.query_one("#mounted-list", ListView)
        m_list.clear()

        code, out, _ = run_command(["su", "-c", "ls /data/local/tmp/enhancify 2>/dev/null"])
        mounted_pkgs = [l.replace(".apk", "").strip() for l in out.splitlines() if l.strip().endswith(".apk")]

        if not mounted_pkgs:
            m_list.append(ListItem(Label(Text("No mounted applications found in /data/local/tmp/enhancify.", style=palette()["muted"]))))
            return

        pal = palette()
        for idx, pkg in enumerate(mounted_pkgs):
            txt = Text()
            txt.append("🔒 ", style=f"bold {pal['danger']}")
            txt.append(f"{pkg:<30}", style=f"bold {pal['text']}")
            txt.append(" [Mounted]", style=pal["accent"])

            item = ListItem(Label(txt))
            item.pkg_name = pkg
            m_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        pkg = getattr(event.item, "pkg_name", None)
        if pkg:
            self.confirm_unmount(pkg)

    def confirm_unmount(self, pkg: str) -> None:
        def handle_confirm(yes: bool) -> None:
            if yes:
                umount_script = env.workspace_dir / "system" / "umount.sh"
                if umount_script.exists():
                    cmd = ["su", "-mm", "-c", f"/system/bin/sh {umount_script} {pkg}"]
                    code, out, err = run_command(cmd, timeout=15)
                    self.populate_mounted()
                    if code == 0:
                        self.app.push_screen(MessageDialog("Unmounted", f"✓ {pkg} unmounted successfully!"))
                    else:
                        self.app.push_screen(MessageDialog("Error", f"Unmount failed: {err or out}"))

        self.app.push_screen(
            ConfirmDialog("Confirm Unmount", f"Are you sure you want to unmount {pkg}?", yes_label="Unmount", no_label="Cancel"),
            handle_confirm,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()

    def action_back(self) -> None:
        self.app.pop_screen()
