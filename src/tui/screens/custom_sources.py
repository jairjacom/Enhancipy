"""
Enhancify Custom Sources Management Screen
Allows adding, editing, and deleting user custom patch sources.
"""

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.assets import assets_mgr
from src.config import DEFAULT_CONFIG, config
from src.sources import SourceInfo, sources_mgr
from src.tui.screens.base import BaseScreen
from src.theme import palette
from src.tui.widgets.dialogs import ConfirmDialog, InputDialog, MessageDialog
from src.tui.widgets.button_bar import ButtonBar


class CustomSourcesScreen(BaseScreen):
    """Custom sources CRUD manager screen."""

    BINDINGS = [
        ("a", "add_source", "Add Source"),
        ("h", "help", "Help"),
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="card list-card"):
            yield Label("➕ Custom Sources Management", classes="card-title")
            yield Label("Add or manage custom ReVanced / Morphe patch repositories and imported patch files:", classes="card-desc")

            with ButtonBar():
                yield Button("➕ Add New Source [A]", id="btn-add", classes="btn-primary")
                yield Button("📖 Description & Help [H]", id="btn-help")
                yield Button("🔙 Back [B]", id="btn-back", classes="btn-secondary")

            yield ListView(id="custom-sources-list")

    def on_mount(self) -> None:
        self.populate_custom_sources()

    def populate_custom_sources(self) -> None:
        """Populate list of custom sources."""
        c_list = self.query_one("#custom-sources-list", ListView)
        c_list.clear()

        all_sources = sources_mgr.get_all_sources()
        custom_sources = [s for s in all_sources if s.is_custom or s.is_local]

        if not custom_sources:
            c_list.append(ListItem(Label(Text("No custom or imported sources yet. Click 'Add New Source' or use Import Patch File on the source list.", style=palette()["muted"]))))
            return

        pal = palette()
        for idx, s in enumerate(custom_sources):
            txt = Text()
            if s.is_local:
                txt.append("📂 ", style=f"bold {pal['tag']}")
                txt.append(f"{s.source:<20}", style=f"bold {pal['text']}")
                bv = s.bundle_version if s.bundle_version.startswith("v") else f"v{s.bundle_version}"
                txt.append(f" ({bv})", style=pal['accent_2'])
                txt.append(" [LOCAL]", style=f"bold {pal['tag']}")
            else:
                txt.append("📦 ", style=f"bold {pal['tag']}")
                txt.append(f"{s.source:<20}", style=f"bold {pal['text']}")
                txt.append(f" ({s.repository})", style=pal['accent_2'])
                if s.json_url:
                    txt.append(" [JSON API]", style=pal['accent'])

            item = ListItem(Label(txt))
            item.source_idx = idx
            c_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = getattr(event.item, "source_idx", None)
        if idx is None and 0 <= event.index:
            idx = event.index
        if idx is not None:
            custom_sources = [s for s in sources_mgr.get_all_sources() if s.is_custom or s.is_local]
            if 0 <= idx < len(custom_sources):
                self.prompt_source_actions(custom_sources[idx])

    def prompt_source_actions(self, source: SourceInfo) -> None:
        """Show Edit / Delete confirmation."""
        def handle_confirm(delete_it: bool) -> None:
            if not delete_it:
                return
            if source.is_local:
                ok, msg = sources_mgr.delete_local_source(source.source)
                assets_mgr.remove_local_bundle(source.source)
                if config.get("SOURCE") == source.source:
                    config.set("SOURCE", DEFAULT_CONFIG["SOURCE"])
                    self.app.multi_sources = [DEFAULT_CONFIG["SOURCE"]]
            else:
                ok, msg = sources_mgr.delete_custom_source(source.source)
            self.populate_custom_sources()
            self.app.push_screen(MessageDialog("Deleted", msg))

        if source.is_local:
            message = (
                f"Imported patch file\nVersion: {source.bundle_version}\n"
                f"Patcher: {source.patcher_version or 'unknown'}\n\n"
                "Do you want to DELETE this local source and its files?"
            )
        else:
            message = f"Repository: {source.repository}\nJSON URL: {source.json_url or 'None'}\n\nDo you want to DELETE this custom source?"

        self.app.push_screen(
            ConfirmDialog(
                title=f"Manage {source.source}",
                message=message,
                yes_label="Delete",
                no_label="Cancel",
            ),
            handle_confirm,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-add":
            self.action_add_source()
        elif btn_id == "btn-help":
            self.action_help()
        elif btn_id == "btn-back":
            self.action_back()

    def action_add_source(self) -> None:
        """Sequential dialogs to add custom source."""
        def step1_name(name_res: Optional[str]) -> None:
            if not name_res or not name_res.strip():
                return
            src_name = name_res.strip()

            def step2_repo(repo_res: Optional[str]) -> None:
                if not repo_res or not repo_res.strip():
                    return
                repo_name = repo_res.strip()

                def step3_json(json_res: Optional[str]) -> None:
                    json_url = json_res.strip() if json_res else ""
                    ok, msg = sources_mgr.add_custom_source(src_name, repo_name, json_url)
                    self.populate_custom_sources()
                    self.app.push_screen(MessageDialog("Result", msg))

                self.app.push_screen(
                    InputDialog("Custom Source JSON (Optional)", "Enter patches.json raw URL (leave blank for CLI parsing):"),
                    step3_json,
                )

            self.app.push_screen(
                InputDialog("Custom Source Repository", "Enter GitHub repository (username/repo):", placeholder="e.g. Aunali321/ReVancedExperiments"),
                step2_repo,
            )

        self.app.push_screen(
            InputDialog("Custom Source Name", "Enter name for this custom source:", placeholder="e.g. MyExperiments"),
            step1_name,
        )

    def action_help(self) -> None:
        help_text = (
            "How to add custom sources:\n\n"
            "1. Source Name: Unique identifier for this patcher profile.\n"
            "2. Repository: Format 'owner/repo' containing patch releases.\n"
            "3. JSON URL (Optional): Raw link to patches-list.json file.\n"
            "   Adding this speeds up patch metadata loading."
        )
        self.app.push_screen(MessageDialog("Custom Sources Guide", help_text))

    def action_back(self) -> None:
        self.app.pop_screen()
