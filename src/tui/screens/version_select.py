"""
Enhancify Version Selection & Downloader Screen
Fetches available APKMirror versions for the chosen app, tags recommended & installed versions,
and downloads the chosen APK or APKM bundle before proceeding to patch selection.
"""

import shutil
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Label, ListItem, ListView

from src.antisplit import antisplit_mgr
from src.assets import assets_mgr
from src.apkmirror import (
    APKMIRROR_BASE,
    APKMirrorBlocked,
    ScrapedVersion,
    apkmirror_scraper,
    browser_download_dirs,
    snapshot_downloads,
    wait_for_browser_download,
)
from src.environment import env
from src.config import config
from src.theme import palette
from src.utils import open_in_browser
from src.tui.screens.base import BaseScreen
from src.tui.widgets.dialogs import (
    ConfirmDialog,
    DownloadProgressModal,
    MessageDialog,
    ProgressModal,
    ThreeChoiceDialog,
)
from src.tui.widgets.button_bar import ButtonBar


class VersionSelectScreen(BaseScreen):
    """Screen for selecting app version to download."""

    BINDINGS = [
        ("a", "auto_select", "Auto Recommended"),
        ("r", "refresh", "Refresh List"),
        ("b", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.versions_list: List[ScrapedVersion] = []
        self.blocked = False
        self.browser_mode = False

    def compose_content(self) -> ComposeResult:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "App")

        with Vertical(classes="card list-card"):
            yield Label(f"📦 Select Version for [bold $enh-accent]{app_name}[/]", classes="card-title")
            yield Label("Select a version from APKMirror. [RECOMMENDED] versions are tested by patch developers:", classes="card-desc")

            with ButtonBar():
                yield Button("⚡ Auto Recommended [A]", id="btn-auto", classes="btn-primary")
                yield Button("🔄 Refresh List [R]", id="btn-refresh")
                yield Button("🔙 Back [B]", id="btn-back", classes="btn-secondary")

            yield ListView(id="versions-list")

    def on_mount(self) -> None:
        self.load_versions()

    def load_versions(self, force_refresh: bool = False) -> None:
        """Fetch version list."""
        self.blocked = False
        self.browser_mode = False
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")
        apkmirror_name = app_info.get("apkmirrorAppName", app_name.lower())
        supported = app_info.get("versions", [])

        modal = ProgressModal("Loading Versions", f"Fetching versions for {app_name} from APKMirror...")
        self.app.push_screen(modal)
        self.run_versions_worker(modal, apkmirror_name, supported, force_refresh)

    @work(thread=True)
    def run_versions_worker(
        self,
        modal: ProgressModal,
        apkmirror_name: str,
        supported: List[str],
        force_refresh: bool,
    ) -> None:
        try:
            try:
                self.versions_list = apkmirror_scraper.fetch_versions_list(
                    apkmirror_name,
                    supported_versions=supported,
                    force_refresh=force_refresh,
                )
            except APKMirrorBlocked:
                self.versions_list = []
                self.blocked = True
        finally:
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(self.populate_versions_list)

    def populate_versions_list(self) -> None:
        """Populate the ListView with versions."""
        v_list = self.query_one("#versions-list", ListView)
        v_list.clear()

        if not self.versions_list:
            if self.blocked:
                v_list.append(ListItem(Label(Text(
                    "APKMirror is blocking automatic downloads for this app (Cloudflare browser check).",
                    style=palette()["danger"],
                ))))
                self._offer_browser_fallback()
            elif self.browser_mode:
                v_list.append(ListItem(Label(Text(
                    "Couldn't get versions from APKMirror's API. Check your connection and press Refresh.",
                    style=palette()["danger"],
                ))))
            else:
                v_list.append(ListItem(Label(Text("No versions found. Check internet connection or APKMirror name.", style=palette()["danger"]))))
            return

        pal = palette()
        for idx, v in enumerate(self.versions_list):
            txt = Text()
            txt.append("📌 ", style=f"bold {pal['accent']}")
            txt.append(f"{v.version:<20}", style=f"bold {pal['text']}")

            if v.tag == "[RECOMMENDED]":
                txt.append(" [RECOMMENDED]", style=f"bold {pal['accent']}")
            elif v.tag == "[INSTALLED]":
                txt.append(" [INSTALLED]", style=f"bold {pal['accent_2']}")
            elif v.tag == "[BETA]":
                txt.append(" [BETA]", style=pal["warning"])
            elif v.tag == "[ALPHA]":
                txt.append(" [ALPHA]", style=pal["danger"])
            else:
                txt.append(" [STABLE]", style=pal["muted"])
            if v.note:
                txt.append(f"  {v.note}", style=pal["muted"])

            item = ListItem(Label(txt))
            item.version_idx = idx
            v_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = getattr(event.item, "version_idx", None)
        if idx is None and 0 <= event.index < len(self.versions_list):
            idx = event.index
        if idx is not None and 0 <= idx < len(self.versions_list):
            selected_v = self.versions_list[idx]
            self.download_and_proceed(selected_v)

    def download_and_proceed(self, selected_version: ScrapedVersion) -> None:
        """Entry point for a chosen version.

        Classic bash parity (modules/patch.sh findPatchedApp + modules/app/
        download.sh downloadApp): before touching the network, check whether
        this version was already patched or already downloaded/merged, and
        let the user choose to reuse it instead of redoing the work.
        """
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")
        source_name = config.get("SOURCE", "Anddea")
        app_dir = apkmirror_scraper.apps_dir / app_name
        version = selected_version.version

        patched_path = app_dir / f"{version}-{source_name}.apk"
        if patched_path.exists():
            self.app.push_screen(
                ThreeChoiceDialog(
                    "| Patched APK Found |",
                    f"Current directory already contains a patched {app_name} "
                    f"version {version}.\n\nDo you want to patch it again?",
                    choices=[
                        ("patch", "🔨 Patch Again", "btn-primary"),
                        ("install", "📲 Install", "btn-secondary"),
                        ("back", "🔙 Back", "btn-secondary"),
                    ],
                ),
                lambda result: self._on_patched_choice(result, selected_version, app_dir, patched_path),
            )
            return

        self._check_raw_apk(selected_version, app_dir)

    def _on_patched_choice(
        self,
        result: Optional[str],
        selected_version: ScrapedVersion,
        app_dir: Path,
        patched_path: Path,
    ) -> None:
        if result == "install":
            raw_path = app_dir / f"{selected_version.version}.apk"
            self.app.selected_app["version"] = selected_version.version
            self.app.selected_app["apk_path"] = raw_path if raw_path.exists() else None
            self.app.selected_app["skip_patch"] = True
            self.app.push_screen("patch_progress_screen")
        elif result == "patch":
            patched_path.unlink(missing_ok=True)
            self._check_raw_apk(selected_version, app_dir)
        # "back" / dismissed (Escape) — stay on the version list, nothing to do

    def _check_raw_apk(self, selected_version: ScrapedVersion, app_dir: Path) -> None:
        version = selected_version.version
        raw_path = app_dir / f"{version}.apk"

        if raw_path.exists():
            app_info = getattr(self.app, "selected_app", {})
            app_name = app_info.get("appName", "")
            self.app.push_screen(
                ConfirmDialog(
                    "| App Found |",
                    f"{app_name} {version}.apk already exists.\n\n"
                    f"Download and merge again?",
                    yes_label="🔄 Download Again",
                    no_label="♻ Reuse Existing",
                ),
                lambda confirmed: self._on_raw_apk_choice(confirmed, selected_version, app_dir, raw_path),
            )
            return

        # Nothing for this version — prune leftovers from a different
        # version/source so the merge step never sees a stale output path
        # (classic bash: `rm -rf apps/$APP_NAME` when nothing matches $APP_VER*).
        if app_dir.exists() and not any(p.name.startswith(version) for p in app_dir.iterdir()):
            shutil.rmtree(app_dir, ignore_errors=True)

        self._start_download(selected_version)

    def _on_raw_apk_choice(
        self,
        download_again: bool,
        selected_version: ScrapedVersion,
        app_dir: Path,
        raw_path: Path,
    ) -> None:
        if download_again:
            shutil.rmtree(app_dir, ignore_errors=True)
            self._start_download(selected_version)
        else:
            self.app.selected_app["version"] = selected_version.version
            self.app.selected_app["apk_path"] = raw_path
            self.app.push_screen("patch_select_screen")

    def _start_download(self, selected_version: ScrapedVersion) -> None:
        """Download APK / APKM from APKMirror, process antisplit, and proceed to patch screen."""
        if self.browser_mode:
            self._start_browser_download(selected_version)
            return
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")

        # Original bash scrape gauge text
        modal = DownloadProgressModal.for_app_scrape(app_name, selected_version.version)
        self.app.push_screen(modal)
        self.run_download_worker(modal, selected_version)

    @work(thread=True)
    def run_download_worker(
        self, modal: DownloadProgressModal, selected_version: ScrapedVersion
    ) -> None:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")

        try:
            # 1. Scrape link
            dl_info = apkmirror_scraper.scrape_download_link(selected_version.url)
            if modal.was_cancelled:
                self.app.call_from_thread(modal.safe_dismiss, "cancelled")
                return
            if not dl_info:
                self.app.call_from_thread(modal.safe_dismiss)
                self.app.call_from_thread(
                    self.app.push_screen,
                    MessageDialog(
                        "Download Error",
                        f"Failed to scrape download link for {selected_version.version}!",
                    ),
                )
                return

            dl_url, app_format, size_bytes, ext = dl_info

            # 2. Switch body to original File/Size/Downloading... text + start download
            modal.switch_to_app_download(
                app_name, selected_version.version, ext, size_bytes
            )

            downloaded_file = apkmirror_scraper.download_app(
                app_name,
                selected_version.version,
                dl_url,
                ext,
                size_bytes,
                progress_callback=modal.on_progress,
                cancel_event=modal.cancel_event,
            )

            if modal.was_cancelled:
                self.app.call_from_thread(modal.safe_dismiss, "cancelled")
                self.app.call_from_thread(
                    self.app.push_screen,
                    MessageDialog("Cancelled", "App download cancelled."),
                )
                return

            if not downloaded_file or not downloaded_file.exists():
                self.app.call_from_thread(modal.safe_dismiss)
                self.app.call_from_thread(
                    self.app.push_screen,
                    MessageDialog(
                        "Download Failed",
                        "Download failed. Check your internet connection and retry.",
                    ),
                )
                return

            self._finish_downloaded_app(modal, downloaded_file, selected_version.version, ext)
        except APKMirrorBlocked:
            # e.g. a version list cached before APKMirror started challenging this app.
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(self._offer_browser_fallback, selected_version)
        except Exception as e:
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(
                self.app.push_screen,
                MessageDialog("Error", f"Error during download process: {e}"),
            )

    def _finish_downloaded_app(
        self, modal: DownloadProgressModal, downloaded_file: Path, version: str, ext: str
    ) -> None:
        """Antisplit / optimize a downloaded app file, then proceed to patch selection.
        Runs in a worker thread."""
        # 3. Antisplit or optimize native libs
        target_apk = downloaded_file.parent / f"{version}.apk"

        if ext == "apkm":
            modal.update_message("Merging APKM bundle splits with APKEditor...")
            ok = antisplit_mgr.antisplit_apkm(downloaded_file, target_apk)
            if not ok:
                self.app.call_from_thread(modal.safe_dismiss)
                self.app.call_from_thread(
                    self.app.push_screen,
                    MessageDialog("Merge Error", "Failed to merge APKM splits!"),
                )
                return
        elif ext == "apk" and config.is_on("OPTIMIZE_LIBS"):
            modal.update_message(
                "Optimizing native libraries for device architecture..."
            )
            antisplit_mgr.optimize_native_libs(downloaded_file)

        apk_path = target_apk if target_apk.exists() else downloaded_file

        def apply_result():
            self.app.selected_app["version"] = version
            self.app.selected_app["apk_path"] = apk_path

        self.app.call_from_thread(apply_result)
        self.app.call_from_thread(modal.safe_dismiss)
        self.app.call_from_thread(self.app.push_screen, "patch_select_screen")

    # --- Browser handoff (APKMirror blocks plain HTTP clients with a Cloudflare challenge) ---

    def _offer_browser_fallback(self, selected_version: Optional[ScrapedVersion] = None) -> None:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")
        ver = f" {selected_version.version}" if selected_version else ""
        message = (
            f"APKMirror is showing a Cloudflare browser check for {app_name}{ver}, "
            f"so EnhanciPy can't download it automatically.\n\n"
            f"Use your browser instead: EnhanciPy opens the APKMirror page in your browser "
            f"and continues on its own once the file lands in Downloads."
        )

        def on_choice(use_browser: Optional[bool]) -> None:
            if not use_browser:
                return
            if selected_version is None:
                self.load_browser_versions()
            else:
                self._start_browser_download(selected_version)

        self.app.push_screen(
            ConfirmDialog(
                title="| APKMirror Blocked |",
                message=message,
                yes_label="🌐 Use Browser",
                no_label="🔙 Back",
            ),
            on_choice,
        )

    def load_browser_versions(self) -> None:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")
        modal = ProgressModal("Loading Versions", f"Fetching {app_name} versions from APKMirror's API...")
        self.app.push_screen(modal)
        self.run_browser_versions_worker(modal, app_info.get("pkgName", ""), app_info.get("versions", []))

    @work(thread=True)
    def run_browser_versions_worker(self, modal: ProgressModal, pkg: str, supported: List[str]) -> None:
        try:
            # The patches JSON can omit the version the bundle targets (HushGram's
            # Instagram entry is empty); the bundle itself knows it.
            targets = assets_mgr.target_versions(config.get("SOURCE", "Anddea"), pkg)
            supported = list(supported) + [v for v in targets if v not in supported]
            self.versions_list = apkmirror_scraper.fetch_browser_versions(pkg, supported, targets)
            self.browser_mode = True
        finally:
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(self.populate_versions_list)

    def _start_browser_download(self, selected_version: ScrapedVersion) -> None:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")

        dirs = browser_download_dirs()
        if not dirs:
            self.app.push_screen(
                MessageDialog(
                    "Downloads Not Accessible",
                    "EnhanciPy can't read your Downloads folder. "
                    "Run termux-setup-storage in Termux, then try again.",
                )
            )
            return

        url = urllib.parse.urljoin(APKMIRROR_BASE, selected_version.url)
        modal = DownloadProgressModal.for_browser_download(
            app_name, selected_version.version, env.get_arch(), url, selected_version.note
        )
        self.app.push_screen(modal)
        self.run_browser_download_worker(modal, selected_version, url, dirs)

    @work(thread=True)
    def run_browser_download_worker(
        self,
        modal: DownloadProgressModal,
        selected_version: ScrapedVersion,
        url: str,
        dirs: List[Path],
    ) -> None:
        app_info = getattr(self.app, "selected_app", {})
        app_name = app_info.get("appName", "")
        pkg = app_info.get("pkgName", "")

        try:
            # Snapshot before opening the browser so pre-existing files are ignored.
            before = snapshot_downloads(dirs)
            if not open_in_browser(url):
                modal.update_message("Couldn't open the browser. Open the link above manually.")

            meta = wait_for_browser_download(
                pkg, modal.cancel_event, dirs, before, status_callback=modal.update_message
            )

            if modal.was_cancelled:
                self.app.call_from_thread(modal.safe_dismiss, "cancelled")
                self.app.call_from_thread(
                    self.app.push_screen,
                    MessageDialog("Cancelled", "App download cancelled."),
                )
                return

            if meta is None:
                self.app.call_from_thread(modal.safe_dismiss)
                self.app.call_from_thread(
                    self.app.push_screen,
                    MessageDialog(
                        "Browser Download",
                        f"No {app_name} download showed up in Downloads within 15 minutes.\n\n"
                        "Try again, or use Import on the app list to pick the file yourself.",
                    ),
                )
                return

            # The real file's version wins if the user downloaded a different one.
            version = meta.version_name or selected_version.version
            downloaded = apkmirror_scraper.adopt_browser_download(
                app_name, version, meta.file_path, meta.extension
            )
            self._finish_downloaded_app(modal, downloaded, version, meta.extension)
        except Exception as e:
            self.app.call_from_thread(modal.safe_dismiss)
            self.app.call_from_thread(
                self.app.push_screen,
                MessageDialog("Error", f"Error during download process: {e}"),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-auto":
            self.action_auto_select()
        elif btn_id == "btn-refresh":
            self.action_refresh()
        elif btn_id == "btn-back":
            self.action_back()

    def action_auto_select(self) -> None:
        """Find first recommended version and select it."""
        for v in self.versions_list:
            if v.tag == "[RECOMMENDED]":
                self.download_and_proceed(v)
                return
        if self.versions_list:
            self.download_and_proceed(self.versions_list[0])

    def action_refresh(self) -> None:
        self.load_versions(force_refresh=True)

    def action_back(self) -> None:
        self.app.pop_screen()
