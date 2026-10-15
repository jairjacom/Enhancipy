"""
Enhancify Patch Options Configuration Screen
Allows users to customize patch settings (e.g., custom branding name, API URLs, toggles)
with type-safe input dialogs before launching the patcher.
"""

import re
from typing import Any, Dict, List, Optional, Set

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.config import config
from src.theme import palette
from src.patches import patches_mgr
from src.tui.screens.base import BaseScreen
from src.tui.widgets.dialogs import ChecklistDialog, ConfirmDialog, InputDialog, MessageDialog, SelectDialog
from src.tui.widgets.button_bar import ButtonBar


_LIST_TOKEN = re.compile(r"^[A-Za-z0-9+_.\-]+$")


def _tokens(text: str) -> List[str]:
    return [t.strip() for t in text.split(",")]


def comma_list_items(opt: Dict[str, Any]) -> Optional[List[str]]:
    """Checklist items for a comma-separated String option, else None.

    Qualifies when type is String, `values` is not a non-empty dict, and the
    default is a str of >=2 comma-separated, non-empty tokens that all match
    _LIST_TOKEN and are not all digits (number lists such as double-tap
    lengths accept custom values, so they keep the text field). Result:
    default tokens in order, then any extra tokens from the current value
    (if a str), in their order.
    """
    if opt.get("type") != "String":
        return None
    values = opt.get("values")
    if isinstance(values, dict) and values:
        return None
    default = opt.get("default")
    if not isinstance(default, str):
        return None
    base = _tokens(default)
    if len(base) < 2 or not all(t and _LIST_TOKEN.match(t) for t in base):
        return None
    if all(t.isdigit() for t in base):
        return None
    items = list(base)
    value = opt.get("value")
    if isinstance(value, str):
        for t in _tokens(value):
            if t and t not in items:
                items.append(t)
    return items


class OptionsEditScreen(BaseScreen):
    """Screen for configuring patch options."""

    BINDINGS = [
        ("s", "start_patching", "Start Patching"),
        ("r", "reset_defaults", "Reset Defaults"),
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.options_list: List[Dict[str, Any]] = []

    def compose_content(self) -> ComposeResult:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "App")

        with Vertical(classes="card list-card"):
            yield Label(f"⚙️ Configure Patch Options for [bold $enh-accent]{app_name}[/]", classes="card-title")
            yield Label("Select an option below to modify its value, or proceed to start patching:", classes="card-desc")

            with ButtonBar():
                yield Button("🚀 Start Patching [S]", id="btn-start", classes="btn-primary")
                yield Button("🔄 Reset Defaults [R]", id="btn-reset")
                yield Button("🔙 Back [B]", id="btn-back", classes="btn-secondary")

            yield ListView(id="options-list")

    def on_mount(self) -> None:
        self.load_options()

    def load_options(self) -> None:
        """Load and filter options for enabled patches."""
        app_info = getattr(self.app, "selected_app", {})
        enabled_patches: Set[str] = app_info.get("enabled_patches", set())
        available_options: List[Dict[str, Any]] = app_info.get("available_options", [])
        source_name = config.get("SOURCE", "Anddea")
        pkg_name = app_info.get("pkgName", "")

        # Filter options for enabled patches
        filtered = []
        for opt in available_options:
            if opt.get("patchName") in enabled_patches:
                filtered.append({
                    "patchName": opt.get("patchName"),
                    "key": opt.get("key"),
                    "title": opt.get("title", opt.get("key")),
                    "description": opt.get("description", ""),
                    "type": opt.get("type", "String"),
                    "default": opt.get("default"),
                    "value": opt.get("value", opt.get("default")),
                    "values": opt.get("values") or {},
                })

        self.options_list = filtered
        self.populate_options()

    def populate_options(self) -> None:
        """Populate ListView with configured options."""
        o_list = self.query_one("#options-list", ListView)
        o_list.clear()

        if not self.options_list:
            o_list.append(ListItem(Label(Text("No configurable options for enabled patches. You can proceed directly!", style=palette()["accent"]))))
            return

        pal = palette()
        for idx, opt in enumerate(self.options_list):
            title = opt["title"]
            pn = opt["patchName"]
            val = opt["value"]
            opt_type = opt["type"]

            txt = Text()
            txt.append("⚙️ ", style=f"bold {pal['accent_2']}")
            txt.append(f"{title:<30}", style=f"bold {pal['text']}")
            txt.append(f" ({pn})", style=pal["muted"])
            txt.append(f" = [ {val} ]", style=f"bold {pal['accent']}")

            item = ListItem(Label(txt))
            item.opt_idx = idx
            o_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = getattr(event.item, "opt_idx", None)
        if idx is None and 0 <= event.index < len(self.options_list):
            idx = event.index
        if idx is not None and 0 <= idx < len(self.options_list):
            opt = self.options_list[idx]
            self.edit_option(opt, idx)

    def edit_option(self, opt: Dict[str, Any], idx: int) -> None:
        """Open editor dialog for option."""
        opt_type = opt["type"]
        title = opt["title"]
        desc = opt["description"]
        cur_val = str(opt["value"] if opt["value"] is not None else "")

        presets = opt.get("values")

        if opt_type == "Boolean":
            # Toggle boolean directly or confirm
            new_val = not bool(opt["value"])
            self.options_list[idx]["value"] = new_val
            self.populate_options()
        elif isinstance(presets, dict) and presets:
            def handle_select(res: Optional[str]) -> None:
                if res is not None:
                    self.options_list[idx]["value"] = res
                    self.populate_options()

            self.app.push_screen(
                SelectDialog(
                    title=f"Edit {title}",
                    prompt=desc,
                    choices=list(presets.items()),
                    current_value=opt["value"],
                ),
                handle_select,
            )
        # StringArray options (list default) keep the free-text InputDialog below.
        elif (items := comma_list_items(opt)):
            cur = opt["value"]
            selected = (
                [t for t in _tokens(cur) if t]
                if isinstance(cur, str) and cur.strip()
                else _tokens(opt["default"])
            )

            def handle_checklist(res: Optional[List[str]]) -> None:
                if res is not None:
                    self.options_list[idx]["value"] = ", ".join(res)
                    self.populate_options()

            self.app.push_screen(
                ChecklistDialog(
                    title=f"Edit {title}",
                    prompt=desc,
                    items=items,
                    selected=selected,
                ),
                handle_checklist,
            )
        else:
            def handle_input(res: Optional[str]) -> None:
                if res is not None:
                    if opt_type == "Number":
                        try:
                            self.options_list[idx]["value"] = int(res) if res else None
                        except ValueError:
                            self.app.push_screen(MessageDialog("Invalid Input", "Field must be a valid number!"))
                            return
                    else:
                        self.options_list[idx]["value"] = res if res != "" else None
                    self.populate_options()

            self.app.push_screen(
                InputDialog(
                    title=f"Edit {title}",
                    prompt=f"{desc}\n\nType: {opt_type}",
                    initial_value=cur_val,
                ),
                handle_input,
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-start":
            self.action_start_patching()
        elif btn_id == "btn-reset":
            self.action_reset_defaults()
        elif btn_id == "btn-back":
            self.action_back()

    def action_reset_defaults(self) -> None:
        for opt in self.options_list:
            opt["value"] = opt["default"]
        self.populate_options()

    def action_start_patching(self) -> None:
        """Save selections and launch patch progress screen."""
        app_info = getattr(self.app, "selected_app", {})
        source_name = config.get("SOURCE", "Anddea")
        pkg_name = app_info.get("pkgName", "")
        enabled_patches = app_info.get("enabled_patches", set())

        # Persist to disk
        patches_mgr.save_pkg_selection(source_name, pkg_name, enabled_patches, self.options_list)

        self.app.selected_app["configured_options"] = self.options_list
        self.app.push_screen("patch_progress_screen")

    def action_back(self) -> None:
        self.app.pop_screen()
