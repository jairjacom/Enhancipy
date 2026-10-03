"""Shared window chrome for every EnhanciPy screen (except the boot splash)."""
from typing import TypeVar

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer

from src.environment import env
from src.tui.widgets.content_container import ContentContainer
from src.tui.widgets.header import CyberHeader
from src.tui.widgets.status_bar import CyberStatusBar

T = TypeVar("T")


class BaseScreen(Screen[T]):
    """Uniform window: CyberHeader → scrollable ContentContainer → Footer.

    Subclasses implement compose_content(); everything it yields lands inside
    ContentContainer(classes="container-box"). BaseScreen computes the
    privilege/network info once and stores it for subclasses to reuse.
    """

    SHOW_STATUS_BAR = False  # only MainMenuScreen sets True

    def compose(self) -> ComposeResult:
        self.priv = env.check_privileges()          # (has_root, has_rish, mode_label)
        _, _, net_status = env.check_network()
        yield CyberHeader(mode_label=self.priv[2], online_status=net_status)
        if self.SHOW_STATUS_BAR:
            yield CyberStatusBar(
                mode_label=self.priv[2],
                online_status=net_status,
                arch=env.get_arch(),
            )
        with ContentContainer(classes="container-box"):
            yield from self.compose_content()
        yield Footer()

    def compose_content(self) -> ComposeResult:
        raise NotImplementedError
        yield  # pragma: no cover — makes this a generator for ComposeResult typing
