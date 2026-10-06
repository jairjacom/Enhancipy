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


def mode_badge_class(mode_label: str) -> str:
    """Color class for the privilege badge; "" = neutral (pending/unknown)."""
    if "Root" in mode_label:
        return "badge-green"
    if "Rish" in mode_label:
        return "badge-cyan"
    if mode_label == "Non-privilege Mode":
        return "badge-purple"
    return ""


def net_badge_class(online_status: str) -> str:
    """Color class for the network badge; "" = neutral (pending/unknown)."""
    if online_status == "Online":
        return "badge-green"
    if online_status.startswith("Partial"):
        return "badge-yellow"
    if online_status == "Offline":
        return "badge-red"
    return ""


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
            title_text = Text()
            title_text.append("·· ", style=pal["accent_2"])
            title_text.append("EnhanciPy", style="bold " + pal["accent"])
            title_text.append(" - ", style=pal["border"])
            title_text.append("modded by jair-00", style=pal["text"])
            title_text.append(" ··", style=pal["accent_2"])
            yield Label(title_text, id="header-title")

            source_name = config.get("SOURCE", "Anddea")
            arch = env.get_arch()

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
                yield Label(
                    f"⚙️ {self.mode_label}",
                    id="badge-mode",
                    classes=f"badge {mode_badge_class(self.mode_label)}".strip(),
                )

                # Network badge
                yield Label(
                    f"🌐 {self.online_status}",
                    id="badge-net",
                    classes=f"badge {net_badge_class(self.online_status)}".strip(),
                )

                # Source badge
                yield Label(f"📦 {source_name}", classes="badge badge-purple")

                # Arch badge
                yield Label(f"🤖 {arch}", classes="badge badge-yellow")

    def update_status(self, mode_label: str, online_status: str) -> None:
        """Update header badges dynamically."""
        self.mode_label = mode_label
        self.online_status = online_status
        self.refresh(recompose=True)
