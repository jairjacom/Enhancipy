"""
Enhancify ContentContainer Widget
Scrollable container without ScrollableContainer's arrow-key bindings.
"""

from textual.containers import Container

from src.tui.widgets.pan_scroll import HorizontalPanMixin


class ContentContainer(HorizontalPanMixin, Container):
    """Container with scrolling enabled via CSS, but none of
    ScrollableContainer's baked-in arrow/page-key bindings. Textual merges
    BINDINGS across the whole class hierarchy, so subclassing
    ScrollableContainer and setting BINDINGS = [] does NOT remove its
    inherited scroll bindings — they still intercept arrow keys before
    app-level focus-navigation bindings (EnhancifyApp.BINDINGS) ever see
    them, whenever there's remaining scroll room (e.g. on-screen keyboard
    open). Starting from plain Container (which has no BINDINGS at all)
    and only borrowing the scrollable overflow CSS avoids that."""

    DEFAULT_CSS = """
    ContentContainer {
        overflow-y: auto;
        overflow-x: auto;
    }
    """

    can_focus = False
