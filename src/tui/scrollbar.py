"""Arrow-decorated scrollbar rendering (▲▼ vertical, ◀▶ horizontal)."""

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBarRender


class ArrowScrollBarRender(ScrollBarRender):
    """ScrollBarRender that draws clickable arrow glyphs at both ends.

    Glyphs use bar_color (the theme's scrollbar-color / scrollbar-color-hover
    token) on back_color, so every theme gets them for free and they recolor
    on hover exactly like the thumb.
    """

    UP = "▲"
    DOWN = "▼"
    LEFT = "◀"
    RIGHT = "▶"
    MIN_SIZE = 3  # below this, arrows would consume the whole track

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
        rendered = super().render_bar(
            size=size,
            virtual_size=virtual_size,
            window_size=window_size,
            position=position,
            thickness=thickness,
            vertical=vertical,
            back_color=back_color,
            bar_color=bar_color,
        )
        segments = rendered.segments
        has_overflow = bool(window_size and size and virtual_size and size != virtual_size)
        if not (has_overflow and size >= cls.MIN_SIZE):
            return rendered

        if vertical:
            # One segment per row; ends are track rows (or thumb at extremes).
            segments[0] = Segment(
                cls.UP * thickness,
                Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "scroll_up"}),
            )
            segments[-1] = Segment(
                cls.DOWN * thickness,
                Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "scroll_down"}),
            )
        else:
            # Stock layout is (row_segments + [line]) * thickness, flat list;
            # each row occupies size+1 slots ending in a line segment.
            stride = size + 1
            for row in range(thickness):
                base = row * stride
                segments[base] = Segment(
                    cls.LEFT,
                    Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "scroll_up"}),
                )
                segments[base + size - 1] = Segment(
                    cls.RIGHT,
                    Style(color=bar_color, bgcolor=back_color, meta={"@mouse.down": "scroll_down"}),
                )
        return Segments(segments, new_lines=rendered.new_lines)
