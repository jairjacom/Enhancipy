"""
Touch-friendly horizontal panning for scrollable panels.

Termux turns a finger swipe into mouse-wheel events, and only ever the
vertical kind (wheel up/down); it never emits wheel-left/right. A panel that
only overflows sideways therefore ignored swipes and could be moved solely by
grabbing its scrollbar line. HorizontalPanMixin maps those vertical wheel
events onto horizontal scrolling when the panel has nothing to scroll
vertically, so dragging the panel moves it sideways.
"""

from textual import events
from textual.containers import VerticalScroll


class HorizontalPanMixin:
    """Vertical wheel -> horizontal scroll on panels with sideways-only overflow.

    Vertical content keeps its stock behavior (the wheel scrolls it). Once the
    panel is already at its left/right edge the event is left to bubble, so a
    parent panel can still take it. Shift/ctrl+wheel stays stock too.
    """

    PAN_STEP = 3  # cells moved per wheel event

    def _pan_horizontally(self, event: events.MouseEvent, direction: int) -> None:
        if event.ctrl or event.shift:
            return
        if self.allow_vertical_scroll or not self.allow_horizontal_scroll:
            return
        target = min(max(self.scroll_x + direction * self.PAN_STEP, 0), self.max_scroll_x)
        if target == self.scroll_x:
            return
        self.scroll_to(x=target, animate=False)
        event.stop()
        event.prevent_default()  # skip Widget's own wheel handler

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._pan_horizontally(event, +1)

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._pan_horizontally(event, -1)


class PanScroll(HorizontalPanMixin, VerticalScroll):
    """VerticalScroll that also pans sideways on a vertical swipe."""
