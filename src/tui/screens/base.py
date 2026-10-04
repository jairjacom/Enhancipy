"""Shared window chrome for every EnhanciPy screen (except the boot splash)."""
from typing import Tuple, TypeVar

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer

from src.environment import env
from src.tui.widgets.content_container import ContentContainer
from src.tui.widgets.header import CyberHeader
from src.tui.widgets.status_bar import CyberStatusBar

T = TypeVar("T")

STATUS_PENDING = "Checking..."


class BaseScreen(Screen[T]):
    """Uniform window: CyberHeader → scrollable ContentContainer → Footer.

    Subclasses implement compose_content(); everything it yields lands inside
    ContentContainer(classes="container-box"). compose() never probes: it
    renders the last known privilege/network values (or "Checking..."), and
    on_mount() refreshes them in a worker. Subclasses whose compose_content()
    reads self.priv override privileges_resolved().
    """

    SHOW_STATUS_BAR = False  # only MainMenuScreen sets True

    def compose(self) -> ComposeResult:
        # Never probe here: compose runs on the UI thread. Show the last known
        # values (or "Checking...") and let on_mount() refresh them in a worker.
        self.priv = env.last_privileges() or (False, False, STATUS_PENDING)  # (has_root, has_rish, mode_label)
        self._net_status = env.last_network_status() or STATUS_PENDING
        yield CyberHeader(mode_label=self.priv[2], online_status=self._net_status)
        if self.SHOW_STATUS_BAR:
            yield CyberStatusBar(
                mode_label=self.priv[2],
                online_status=self._net_status,
                arch=env.get_arch(),
            )
        with ContentContainer(classes="container-box"):
            yield from self.compose_content()
        yield Footer()

    def on_mount(self) -> None:
        self._probe_status()

    @work(thread=True)
    def _probe_status(self) -> None:
        priv = env.check_privileges()           # cached after the first probe
        _, _, net_status = env.check_network()  # cached for 30s
        try:
            self.app.call_from_thread(self._apply_status, priv, net_status)
        except Exception:
            pass  # app exited before the probe finished

    def _apply_status(self, priv: Tuple[bool, bool, str], net_status: str) -> None:
        if not self.is_attached:  # screen popped while probing
            return
        if priv == self.priv and net_status == self._net_status:
            return
        self.priv = priv
        self._net_status = net_status
        for header in self.query(CyberHeader):
            header.update_status(priv[2], net_status)
        for bar in self.query(CyberStatusBar):
            bar.update_status(priv[2], net_status)
        self.privileges_resolved(priv)

    def privileges_resolved(self, priv: Tuple[bool, bool, str]) -> None:
        """Hook for subclasses whose compose_content() branched on self.priv;
        called on the UI thread when the worker delivers changed values."""

    def compose_content(self) -> ComposeResult:
        raise NotImplementedError
        yield  # pragma: no cover — makes this a generator for ComposeResult typing
