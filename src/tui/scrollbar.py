"""Thin-line scrollbar rendering with dot ends (│ ┃ vertical, ─ ━ horizontal, • ends)."""

from functools import lru_cache
from math import ceil

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBarRender

from src.theme import blend_hex, contrast_ratio

TRACK_MIN_CONTRAST = 3.0  # WCAG minimum for UI components


@lru_cache(maxsize=64)
def track_color(back: Color, bar: Color) -> Color:
    """Accent hue blended toward the pane until it reaches TRACK_MIN_CONTRAST."""
    back_hex = back.get_truecolor().hex
    bar_hex = bar.get_truecolor().hex
    for step in range(10, 21):  # t = 0.50, 0.55 ... 1.00
        mixed = blend_hex(back_hex, bar_hex, step / 20)
        if contrast_ratio(mixed, back_hex) >= TRACK_MIN_CONTRAST:
            return Color.parse(mixed)
    return bar


class LineScrollBarRender(ScrollBarRender):
    """ScrollBarRender drawing a one-cell line: light track, heavy thumb, dot ends.

    The thumb uses bar_color (the theme's scrollbar-color / -hover / -active
    token) so it recolors on hover; the track is a dimmed mix of the same hue
    that stays visible against back_color.
    """

    VERTICAL_TRACK = "│"
    VERTICAL_THUMB = "┃"
    HORIZONTAL_TRACK = "─"
    HORIZONTAL_THUMB = "━"
    END = "•"
    MIN_SIZE = 3  # below this, dots would consume the whole track

    @classmethod
    def render_bar(
        cls,
        size: int = 25,
        virtual_size: float = 50,
        window_size: float = 20,
        position: float = 0,
        thickness: int = 1,
        vertical: bool = True,
        back_color: Color = Color.parse("#555555"),
        bar_color: Color = Color.parse("bright_magenta"),
    ) -> Segments:
        size = int(size)
        width = thickness if vertical else 1
        has_overflow = bool(window_size and size and virtual_size and size != virtual_size)

        if not has_overflow:
            segments = [Segment(" " * width, Style(bgcolor=back_color))] * size
        else:
            track_glyph = cls.VERTICAL_TRACK if vertical else cls.HORIZONTAL_TRACK
            thumb_glyph = cls.VERTICAL_THUMB if vertical else cls.HORIZONTAL_THUMB

            thumb = min(size, max(1, ceil(window_size * size / virtual_size)))
            scrollable = virtual_size - window_size
            ratio = position / scrollable if scrollable > 0 else 0.0
            start = min(size - thumb, max(0, round((size - thumb) * ratio)))
            end = start + thumb

            track_style = Style(color=track_color(back_color, bar_color), bgcolor=back_color)
            up_track = Segment(track_glyph * width, track_style + Style(meta={"@mouse.down": "scroll_up"}))
            down_track = Segment(track_glyph * width, track_style + Style(meta={"@mouse.down": "scroll_down"}))
            thumb_seg = Segment(
                thumb_glyph * width,
                Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "grab"}),
            )
            segments = [up_track] * start + [thumb_seg] * thumb + [down_track] * (size - end)

            if size >= cls.MIN_SIZE:
                segments[0] = Segment(
                    cls.END * width,
                    Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "scroll_up"}),
                )
                segments[-1] = Segment(
                    cls.END * width,
                    Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "scroll_down"}),
                )

        if vertical:
            return Segments(segments, new_lines=True)
        return Segments((segments + [Segment.line()]) * thickness, new_lines=False)
