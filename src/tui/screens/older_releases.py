"""
Enhancify Older Versions Screen
Lists the newest releases of a remote patch source, downloads the chosen .mpp
and hands it to the Import Patch File flow so it becomes a pinned local source.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.assets import PatchRelease, assets_mgr
from src.config import config
from src.sources import SourceInfo
from src.theme import palette
from src.tui.screens.base import BaseScreen
from src.tui.widgets.button_bar import ButtonBar
from src.tui.widgets.dialogs import ConfirmDialog, MessageDialog, ProgressModal
from src.utils import format_size

HELP_TEXT = (
    "Use an earlier release of a patch source.\n\n"
    "1. The list shows the 5 newest releases that ship a .mpp patch file. "
    "Stable or pre-release follows your Pre-release setting.\n"
    "2. Pick one. EnhanciPy downloads it and imports it as a local source, "
    "e.g. \"Anddea v4.3.0\" with a [LOCAL] tag.\n"
    "3. That local source stays on its version until you delete it in Manage Sources. "
    "The original source keeps updating as usual.\n\n"
    "Good to know:\n"
    "• Saved patch selections belong to the source name, so the imported version "
    "starts with its default patches.\n"
    "• Older patches may need an older CLI. EnhanciPy checks and warns you before "
    "importing if the CLI may not fit."
)


class OlderReleasesScreen(BaseScreen[Optional[Tuple[Path, str]]]):
    """Pick one of the newest releases of ``source``; dismisses with (file, suggested name)."""

    BINDINGS = [
        ("h", "help", "Help"),
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def __init__(self, source: SourceInfo, **kwargs) -> None:
        super().__init__(**kwargs)
        self.source = source
        self.releases: List[PatchRelease] = []

    def compose_content(self) -> ComposeResult:
        with Vertical(classes="card list-card"):
            yield Label(f"🕘 Older Versions — {self.source.source}", classes="card-title")
            yield Label(
                "Pick a release to download. It is imported as a local source that stays on that version:",
                classes="card-desc",
            )

            with ButtonBar():
                yield Button("📖 Description & Help [H]", id="btn-help")
                yield Button("🔙 Back [B]", id="btn-back", classes="btn-secondary")

            if config.is_on("USE_PRE_RELEASE"):
                hint = "[Pre-release] Showing pre-releases"
            else:
                hint = "[Stable] Showing stable releases"
            yield Label(hint, id="channel-hint", classes="card-desc")

            yield ListView(id="releases-list")

    def on_mount(self) -> None:
        self._set_message_row("Loading releases...")
        self._load_releases()

    def _set_message_row(self, text: str) -> None:
        rows = self.query_one("#releases-list", ListView)
        rows.clear()
        rows.append(ListItem(Label(Text(text, style=palette()["muted"]))))

    @work(thread=True)
    def _load_releases(self) -> None:
        result = assets_mgr.fetch_recent_patch_releases(
            self.source.repository, config.is_on("USE_PRE_RELEASE")
        )
        self.app.call_from_thread(self._show_releases, result)

    def _show_releases(self, result: Optional[List[PatchRelease]]) -> None:
        self.releases = result or []
        if result is None:
            self._set_message_row(
                "Couldn't load releases. Check your connection, or add a GitHub token in Settings → GitHub Token."
            )
            return
        if not result:
            kind = "pre-release" if config.is_on("USE_PRE_RELEASE") else "stable"
            self._set_message_row(
                f"No {kind} releases with a .mpp patch file found. Try switching the Pre-release setting."
            )
            return

        pal = palette()
        rows = self.query_one("#releases-list", ListView)
        rows.clear()
        for i, rel in enumerate(result):
            txt = Text()
            txt.append(rel.tag, style=f"bold {pal['text']}")
            txt.append(f"  {rel.published}  {format_size(rel.size)}", style=pal["accent_2"])
            if rel.prerelease:
                txt.append(" [PRE]", style=f"bold {pal['warning']}")
            item = ListItem(Label(txt))
            item.release_idx = i
            rows.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = getattr(event.item, "release_idx", None)
        if idx is None or not (0 <= idx < len(self.releases)):
            return
        rel = self.releases[idx]

        def _on_confirm(confirmed: Optional[bool]) -> None:
            if confirmed:
                modal = ProgressModal("Downloading", f"Downloading {rel.asset_name}...")
                self.app.push_screen(modal)
                self._download(modal, rel)

        self.app.push_screen(
            ConfirmDialog(
                title="Download Older Version",
                message=f"Download {rel.tag} ({format_size(rel.size)}) and import it as a local source?",
                yes_label="Download",
                no_label="Cancel",
            ),
            _on_confirm,
        )

    @work(thread=True)
    def _download(self, modal: ProgressModal, rel: PatchRelease) -> None:
        path: Optional[Path] = None
        try:
            path = assets_mgr.download_patch_release(
                rel,
                progress_callback=lambda cur, tot, pct: modal.update_message(
                    f"Downloading {rel.asset_name} {pct}"
                ),
            )
        except Exception:
            path = None
        finally:
            self.app.call_from_thread(modal.safe_dismiss)
        self.app.call_from_thread(self._on_downloaded, path, rel)

    def _on_downloaded(self, path: Optional[Path], rel: PatchRelease) -> None:
        if path is None:
            self.app.push_screen(
                MessageDialog(
                    "Download Failed",
                    "Couldn't download the patch file. Check your connection and try again.",
                )
            )
            return
        self.dismiss((path, f"{self.source.source} {rel.tag}"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-help":
            self.action_help()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_help(self) -> None:
        self.app.push_screen(MessageDialog("Older Versions Guide", HELP_TEXT))

    def action_back(self) -> None:
        self.dismiss(None)
