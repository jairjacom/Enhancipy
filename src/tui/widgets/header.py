"""
Enhancify Custom Cybernetic Header Widget
Displays branding, system mode badge, network status, architecture, and current source.
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Static
from src.tui.widgets.button_bar import ButtonBar

from src.config import config
from src.environment import env
from src.theme import palette


class CyberHeader(Widget):
    """Custom Header bar for Enhancify."""

    DEFAULT_CSS = """
    CyberHeader {
        dock: top;
        height: auto;
        padding: 0 1;
    }
    #cyber-header {
        /* Vertical defaults to height:1fr, which fights the dock:top
           parent's auto height — pin it to its content. */
        height: auto;
    }
    """

    def __init__(self, mode_label: str = "Non-privilege Mode", online_status: str = "Online", **kwargs):
        super().__init__(**kwargs)
        self.mode_label = mode_label
        self.online_status = online_status

    def compose(self) -> ComposeResult:
        pal = palette()
        with Vertical(id="cyber-header"):
            # ASCII / Stylized title
            title_text = Text("⚡ E N H A N C I F Y ⚡", style="bold " + pal["accent"])
            yield Label(title_text, id="header-title")

            source_name = config.get("SOURCE", "Anddea")
            arch = env.get_arch()
            java_ver, _ = env.detect_java_version()

            # Badge Labels are narrow — keep them on one line at least down
            # to phone widths (the default 78-col threshold would stack all
            # four vertically and eat the whole top of a Termux screen).
            # On ultra-narrow portrait phones they hide entirely (the mode /
            # status / arch info is duplicated by the main-menu status bar).
            with ButtonBar(
                id="status-bar-badges",
                stack_threshold=40,
                hide_when_stacked=True,
            ):
                # Privilege badge
                mode_color = pal["accent"] if "Root" in self.mode_label else pal["accent_2"] if "Rish" in self.mode_label else pal["tag"]
                yield Label(f"⚙️ {self.mode_label}", classes="badge badge-green")

                # Network badge
                net_color = pal["accent"] if self.online_status == "Online" else pal["warning"] if "Partial" in self.online_status else pal["danger"]
                yield Label(f"🌐 {self.online_status}", classes="badge badge-cyan")

                # Source badge
                yield Label(f"📦 {source_name}", classes="badge badge-purple")

                # Arch badge
                yield Label(f"🤖 {arch}", classes="badge badge-yellow")

    def update_status(self, mode_label: str, online_status: str) -> None:
        """Update header badges dynamically."""
        self.mode_label = mode_label
        self.online_status = online_status
        self.refresh(recompose=True)
