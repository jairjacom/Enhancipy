"""
Enhancify Textual Application
Main TUI application class tying all screens, themes, and global events together.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen

from src.config import config
from src.environment import env
from src.theme import THEME_MAP, THEMES, get_current_theme
from src.tui.screens.app_select import AppSelectScreen
from src.tui.screens.boot_screen import BootScreen
from src.tui.screens.bundle_patcher import BundlePatcherScreen
from src.tui.screens.custom_sources import CustomSourcesScreen
from src.tui.screens.dependency_select import DependencySelectScreen
from src.tui.screens.gmscore import GmsCoreScreen
from src.tui.screens.keystore_mgr import KeystoreManagerScreen
from src.tui.screens.main_menu import MainMenuScreen
from src.tui.screens.options_edit import OptionsEditScreen
from src.tui.screens.patch_progress import PatchProgressScreen
from src.tui.screens.patch_select import PatchSelectScreen
from src.tui.screens.pothelper import PotHelperScreen
from src.tui.screens.settings import SettingsScreen
from src.tui.screens.source_select import SourceSelectScreen
from src.tui.screens.specs import SpecsScreen
from src.tui.screens.storage_mgr import StorageManagerScreen
from src.tui.screens.theme_select import ThemeSelectScreen
from src.tui.screens.token_mgr import TokenManagerScreen
from src.tui.screens.unmount import UnmountScreen
from src.tui.screens.version_select import VersionSelectScreen


TCSS_PATH = Path(__file__).resolve().parent / "styles.tcss"


class EnhancifyApp(App):
    """Main Textual Application for Enhancify."""

    TITLE = "Enhancify"
    SUB_TITLE = "The Ultimate Custom Revancify Experience"
    CSS_PATH = TCSS_PATH

    # Default AUTO_FOCUS ("*") lands on the first focusable widget in DOM
    # order, which is the scrollable container itself (it's focusable so it
    # can be scrolled with the keyboard) — not a button. That means arrow
    # keys silently scroll the container by a line at a time instead of
    # moving between options, until something is explicitly touched once.
    # Restricting the selector to actual controls fixes that on every screen.
    AUTO_FOCUS = "Button, ListView, Input"

    BINDINGS = [
        Binding("down", "focus_next_widget", show=False),
        Binding("right", "focus_next_widget", show=False),
        Binding("up", "focus_previous_widget", show=False),
        Binding("left", "focus_previous_widget", show=False),
    ]

    SCREENS = {
        "boot_screen": BootScreen,
        "main_menu_screen": MainMenuScreen,
        "source_select_screen": SourceSelectScreen,
        "app_select_screen": AppSelectScreen,
        "version_select_screen": VersionSelectScreen,
        "patch_select_screen": PatchSelectScreen,
        "options_edit_screen": OptionsEditScreen,
        "patch_progress_screen": PatchProgressScreen,
        "settings_screen": SettingsScreen,
        "theme_select_screen": ThemeSelectScreen,
        "custom_sources_screen": CustomSourcesScreen,
        "keystore_mgr_screen": KeystoreManagerScreen,
        "token_mgr_screen": TokenManagerScreen,
        "storage_mgr_screen": StorageManagerScreen,
        "specs_screen": SpecsScreen,
        "dependency_select_screen": DependencySelectScreen,
        "gmscore_screen": GmsCoreScreen,
        "pothelper_screen": PotHelperScreen,
        "bundle_patcher_screen": BundlePatcherScreen,
        "unmount_screen": UnmountScreen,
    }

    def get_screen(self, screen, screen_class=None):
        """Always create a FRESH screen instance for named screens.

        Textual caches the first instance created from ``App.SCREENS`` and
        reuses it on later ``push_screen("name")`` calls; a screen whose pump
        was closed by an earlier pop never mounts again (on_mount never fires),
        so e.g. the asset-fetch flow would silently never start a second time.
        """
        if isinstance(screen, str) and screen in self.SCREENS:
            screen_cls = self.SCREENS[screen]
            if isinstance(screen_cls, type) and issubclass(screen_cls, Screen):
                return screen_cls()
        return super().get_screen(screen, screen_class)

    def __init__(self, force_root: Optional[bool] = None, force_rish: Optional[bool] = None, **kwargs):
        super().__init__(**kwargs)
        self.force_root = force_root
        self.force_rish = force_rish
        self.selected_app: Dict[str, Any] = {}
        self.multi_sources: List[str] = [config.get("SOURCE", "Anddea")]

    def on_mount(self) -> None:
        """Apply active theme and start with the 'Enhancify Rebranded' boot screen."""
        cur_theme = get_current_theme()
        self.apply_theme(cur_theme.id)
        self.push_screen("boot_screen")

    def on_boot_complete(self) -> None:
        """Called by BootScreen when the splash finishes / is skipped."""
        try:
            top = self.screen_stack[-1] if self.screen_stack else None
            if isinstance(top, BootScreen):
                self.pop_screen()
        except Exception:
            pass
        self.push_screen("main_menu_screen")

    def action_focus_next_widget(self) -> None:
        """Move focus forward, mirroring Tab. Only fires when the focused
        widget doesn't already own the arrow key (e.g. ListView cursor)."""
        if self.screen is not None:
            widget = self.screen.focus_next()
            self._scroll_focused_to_top(widget)

    def action_focus_previous_widget(self) -> None:
        """Move focus backward, mirroring Shift+Tab. See action_focus_next_widget."""
        if self.screen is not None:
            widget = self.screen.focus_previous()
            self._scroll_focused_to_top(widget)

    def _scroll_focused_to_top(self, widget) -> None:
        """Scroll the newly focused widget to the top of its scrollable
        ancestor, instead of Textual's default "just barely visible" scroll.
        On a phone with the on-screen keyboard open, only a few rows of
        terminal remain — pinning focus to the top keeps it visible/orientable
        instead of leaving it ambiguously placed within a tiny viewport."""
        if widget is not None:
            widget.scroll_visible(top=True, animate=False)

    def apply_theme(self, theme_id: str) -> None:
        """Dynamically add theme CSS class to App."""
        # Remove all existing theme classes
        for th in THEMES:
            self.remove_class(th.css_class)

        if theme_id in THEME_MAP:
            target_class = THEME_MAP[theme_id].css_class
            self.add_class(target_class)
        else:
            self.add_class("theme-cyber-green")
