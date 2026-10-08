"""
Enhancify Source Selection Screen
Allows users to switch active patch source, refresh release tags, manage custom sources,
and initiate the app patching flow.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.assets import BundleManifest, assets_mgr
from src.config import config
from src.sources import SourceInfo, sanitize_local_source_name, sources_mgr
from src.tui.screens.base import BaseScreen
from src.tui.screens.file_picker import FilePickerScreen
from src.tui.widgets.dialogs import ConfirmDialog, InputDialog, MessageDialog, ProgressModal
from src.tui.widgets.button_bar import ButtonBar
from src.theme import palette
from src.utils import DownloadResult, download_file_ex


class SourceSelectScreen(BaseScreen):
    """Screen for selecting active patch source or picking sources to start patching."""

    BINDINGS = [
        ("p", "proceed", "Proceed to Apps"),
        ("r", "refresh_tags", "Refresh Tags"),
        ("c", "custom_sources", "Custom Sources"),
        ("i", "import_patch_file", "Import Patch File"),
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def __init__(self, is_patch_flow: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.is_patch_flow = is_patch_flow
        self.selected_multi_sources: List[str] = []
        self.displayed_sources: List[SourceInfo] = []

    def compose_content(self) -> ComposeResult:
        is_multi = config.is_on("ENABLE_MULTIPATCHER")
        current_src = config.get("SOURCE", "Anddea")

        with Vertical(classes="card list-card"):
            if self.is_patch_flow:
                if is_multi:
                    yield Label("🚀 Step 1: Select Patch Sources (Multi-Patcher)", classes="card-title")
                    yield Label("Select up to 3 sources to combine, then click Proceed [P / Enter]:", classes="card-desc")
                else:
                    yield Label("🚀 Step 1: Select Patch Source", classes="card-title")
                    yield Label("Choose a patch source below to load supported applications and proceed:", classes="card-desc")
            else:
                if is_multi:
                    yield Label("📦 Multi-Patcher Mode: Select up to 3 sources", classes="card-title")
                    yield Label("Click sources to toggle selection (1 to 3 sources):", classes="card-desc")
                else:
                    yield Label(f"📦 Active Source: [bold $enh-accent]{current_src}[/]", classes="card-title")
                    yield Label("Select a patch source below or refresh tags from GitHub/GitLab:", classes="card-desc")

            with ButtonBar():
                if self.is_patch_flow or is_multi:
                    yield Button("🚀 Proceed to Apps [P]", id="btn-proceed", classes="btn-primary")
                yield Button("🔄 Refresh Tags [R]", id="btn-refresh-tags", classes="btn-primary" if not (self.is_patch_flow or is_multi) else "")
                yield Button("➕ Custom Sources [C]", id="btn-custom-sources")
                yield Button("📂 Import Patch File [I]", id="btn-import-patch")
                yield Button("🔙 Back [B]", id="btn-back", classes="btn-secondary")

            yield Label("", id="channel-hint", classes="card-desc")

            yield ListView(id="sources-list")

    def on_mount(self) -> None:
        if not self.selected_multi_sources:
            cur = config.get("SOURCE", "Anddea")
            self.selected_multi_sources = [cur]
        self.populate_sources()

    def populate_sources(self) -> None:
        """Populate list of sources honouring the USE_PRE_RELEASE toggle."""
        sources = sources_mgr.get_all_sources()
        self.displayed_sources = sources
        current_src = config.get("SOURCE", "Anddea")
        is_multi = config.is_on("ENABLE_MULTIPATCHER")
        use_pre = config.is_on("USE_PRE_RELEASE")

        sources_list = self.query_one("#sources-list", ListView)
        sources_list.clear()

        pal = palette()
        for s in sources:
            if s.is_local:
                version_str = s.bundle_version if s.bundle_version.startswith("v") else f"v{s.bundle_version}"
                channel = "local"
            else:
                # Channel-aware tag: prerelease when enabled, stable otherwise.
                version_str, channel = sources_mgr.get_display_tag(s.source)
                if not version_str:
                    version_str = "No tag cached"

            if is_multi:
                is_active = s.source in self.selected_multi_sources
            else:
                is_active = (s.source == current_src)

            txt = Text()
            if is_active:
                txt.append("● " if not is_multi else "☑ ", style=f"bold {pal['accent']}")
            else:
                txt.append("○ " if not is_multi else "☐ ", style="dim")

            txt.append(f"{s.source:<20}", style=f"bold {pal['text']}" if is_active else pal["text"])
            if s.is_local:
                txt.append(f" ({version_str})", style=pal["accent_2"])
                txt.append(" [LOCAL]", style=f"bold {pal['tag']}")
            elif version_str == "No tag cached":
                txt.append(f" ({version_str})", style=pal["muted"])
            elif channel == "pre":
                txt.append(f" ({version_str})", style=pal["warning"])
                txt.append(" [PRE]", style=f"bold {pal['warning']}")
            else:
                txt.append(f" ({version_str})", style=pal["accent_2"])

            if s.is_custom:
                txt.append(" [CUSTOM]", style=f"bold {pal['tag']}")

            item = ListItem(Label(txt))
            item.source_name = s.source
            sources_list.append(item)

        # Refresh the channel hint label so the mode is always visible.
        try:
            hint = self.query_one("#channel-hint", Label)
            if use_pre:
                hint.update("[Pre-release] Showing bleeding-edge prerelease tags — Refresh Tags [R] to update.")
            else:
                hint.update("[Stable] Showing stable release tags — Refresh Tags [R] to update.")
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection of a source."""
        source_name = getattr(event.item, "source_name", None)
        if not source_name and 0 <= event.index < len(self.displayed_sources):
            source_name = self.displayed_sources[event.index].source

        if not source_name:
            return

        is_multi = config.is_on("ENABLE_MULTIPATCHER")

        if is_multi:
            if source_name in self.selected_multi_sources:
                if len(self.selected_multi_sources) > 1:
                    self.selected_multi_sources.remove(source_name)
            else:
                if len(self.selected_multi_sources) >= 3:
                    self.selected_multi_sources.pop(0)
                self.selected_multi_sources.append(source_name)

            config.set("SOURCE", self.selected_multi_sources[0])
            self.app.multi_sources = self.selected_multi_sources
            self.populate_sources()
        else:
            config.set("SOURCE", source_name)
            self.app.multi_sources = [source_name]

            if self.is_patch_flow:
                # Proceed directly to AppSelectScreen in patching flow
                from src.tui.screens.app_select import AppSelectScreen
                self.app.push_screen(AppSelectScreen())
            else:
                self.populate_sources()
                self.app.push_screen(
                    MessageDialog("Source Updated", f"Active source set to: {source_name}")
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-proceed":
            self.action_proceed()
        elif btn_id == "btn-refresh-tags":
            self.action_refresh_tags()
        elif btn_id == "btn-custom-sources":
            self.action_custom_sources()
        elif btn_id == "btn-import-patch":
            self.action_import_patch_file()
        elif btn_id == "btn-back":
            self.action_back()

    def action_proceed(self) -> None:
        """Proceed to app selection with selected source(s)."""
        is_multi = config.is_on("ENABLE_MULTIPATCHER")
        if is_multi and self.selected_multi_sources:
            config.set("SOURCE", self.selected_multi_sources[0])
            self.app.multi_sources = self.selected_multi_sources

        from src.tui.screens.app_select import AppSelectScreen
        self.app.push_screen(AppSelectScreen())

    def action_refresh_tags(self) -> None:
        """Trigger background tag refresh."""
        modal = ProgressModal("Refreshing Tags", "Fetching latest tags from GitHub / GitLab...")
        self.app.push_screen(modal)
        self.run_tag_refresh_worker(modal)

    @work(thread=True)
    def run_tag_refresh_worker(self, modal: ProgressModal) -> None:
        try:
            sources_mgr.update_tags(progress_callback=lambda cur, tot, name: modal.update_message(f"Fetching {name} ({cur}/{tot})..."))
        finally:
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(self.populate_sources)

    def action_custom_sources(self) -> None:
        self.app.push_screen("custom_sources_screen")

    # --- Import Patch File (.mpp) as a persistent local source ---

    def action_import_patch_file(self) -> None:
        self.app.push_screen(
            FilePickerScreen(allowed_exts={".mpp"}), self._on_patch_file_picked
        )

    def _on_patch_file_picked(self, path: Optional[Path]) -> None:
        if path is None:
            return
        try:
            manifest = assets_mgr.read_bundle_manifest(path)
        except ValueError as e:
            self.app.push_screen(MessageDialog("Invalid Patch File", str(e)))
            return

        prompt = (
            f"Bundle: {manifest.name} {manifest.version}\n"
            f"Patcher: {manifest.patcher_version or 'unknown'}\n\n"
            "Source name:"
        )
        self.app.push_screen(
            InputDialog(
                "Import Patch File",
                prompt,
                initial_value=sanitize_local_source_name(manifest.name),
            ),
            lambda name: self._on_import_name(path, manifest, name),
        )

    def _on_import_name(self, path: Path, manifest: BundleManifest, name: Optional[str]) -> None:
        name = (name or "").strip()
        if not name:
            return
        err = sources_mgr.validate_local_source_name(name)
        if err:
            self.app.push_screen(MessageDialog("Invalid Name", err))
            return
        existing = sources_mgr.get_local_source(name)
        if existing:
            # Use the stored spelling so a case-variant re-import replaces in place.
            def _on_replace(confirmed: Optional[bool]) -> None:
                if confirmed:
                    self._start_import(path, existing.source, manifest)

            self.app.push_screen(
                ConfirmDialog(
                    title="Replace Local Source",
                    message=f"Replace '{existing.source}' {existing.bundle_version} with {manifest.version}?",
                    yes_label="Replace",
                    no_label="Cancel",
                ),
                _on_replace,
            )
            return
        self._start_import(path, name, manifest)

    def _start_import(self, path: Path, name: str, manifest: BundleManifest) -> None:
        modal = ProgressModal("Importing Patch File", "Checking CLI compatibility...")
        self.app.push_screen(modal)
        self.run_import_worker(modal, path, name, manifest)

    @work(thread=True)
    def run_import_worker(
        self, modal: ProgressModal, path: Path, name: str, manifest: BundleManifest
    ) -> None:
        try:
            pv = manifest.patcher_version
            cli, ok = assets_mgr.select_cli_for_bundle(pv)
            if not ok:
                assets_mgr.adopt_cached_cli_for_bundle(pv)
                cli, ok = assets_mgr.select_cli_for_bundle(pv)
            if not ok:
                modal.update_message("Downloading latest Morphe CLI...")
                rel = assets_mgr.fetch_latest_cli_release(
                    assets_mgr.resolve_cli_repo("mpp", name),
                    config.is_on("USE_PRE_RELEASE"),
                )
                if rel and rel[1]:
                    tag, url, size = rel
                    target = assets_mgr.assets_dir / f"CLI-{tag}.jar"
                    if not target.exists():
                        result = download_file_ex(
                            url,
                            target,
                            size,
                            progress_callback=lambda cur, tot, pct: modal.update_message(
                                f"Downloading CLI-{tag}.jar {pct}"
                            ),
                        )
                        if result == DownloadResult.OK:
                            assets_mgr.save_cli_to_cache(name, tag, target)
                cli, ok = assets_mgr.select_cli_for_bundle(pv)
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(self._on_import_cli_checked, path, name, manifest, cli, ok)
        except Exception as e:
            try:
                self.app.call_from_thread(modal.safe_dismiss)
            except Exception:
                pass
            self.app.call_from_thread(
                self.app.push_screen, MessageDialog("Import Failed", str(e))
            )

    def _on_import_cli_checked(
        self,
        path: Path,
        name: str,
        manifest: BundleManifest,
        cli: Optional[Path],
        ok: bool,
    ) -> None:
        if cli is None:
            self.app.push_screen(
                MessageDialog(
                    "Import Failed",
                    "No Morphe CLI is available and the latest one couldn't be downloaded.\n\n"
                    "Connect to the internet and try again.",
                )
            )
            return
        if ok:
            self._finish_import(path, name, manifest)
            return

        def _on_confirm(confirmed: Optional[bool]) -> None:
            if confirmed:
                self._finish_import(path, name, manifest)

        self.app.push_screen(
            ConfirmDialog(
                title="CLI Mismatch",
                message=(
                    f"This patch file was built for patcher {manifest.patcher_version}, "
                    f"but the best available CLI ({cli.name}) has patcher "
                    f"{assets_mgr.cli_patcher_version(cli)}.\nPatching may fail.\n\nImport anyway?"
                ),
                yes_label="Import",
                no_label="Cancel",
            ),
            _on_confirm,
        )

    def _finish_import(self, path: Path, name: str, manifest: BundleManifest) -> None:
        """UI thread: stage the bundle, persist the source, make it active."""
        try:
            assets_mgr.stage_local_bundle(path, name, manifest)
        except (ValueError, OSError) as e:
            self.app.push_screen(MessageDialog("Import Failed", str(e)))
            return
        ok, msg = sources_mgr.save_local_source(name, manifest.version, manifest.patcher_version)
        if not ok:
            self.app.push_screen(MessageDialog("Import Failed", msg))
            return

        config.set("SOURCE", name)
        self.selected_multi_sources = [name]
        self.app.multi_sources = [name]
        self.populate_sources()

        if self.is_patch_flow:
            from src.tui.screens.app_select import AppSelectScreen
            self.app.push_screen(AppSelectScreen())
        else:
            self.app.push_screen(
                MessageDialog(
                    "Patch File Imported",
                    f"{name} ({manifest.version}) imported and set as the active source.",
                )
            )

    def action_back(self) -> None:
        self.app.pop_screen()
