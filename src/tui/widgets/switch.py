"""
Enhancify Animated Custom Switch Widget
A cyber-styled ON/OFF toggle with an eased knob-sliding animation, gradient
track coloring and glow state — used by the Configure dialogs
(Feature & Optimization Toggles, Rish Installer Flags).

Interaction:
  * Click to toggle
  * Focus + [Enter] / [Space] to toggle
  * `value` reactive carries the logical state (UI dialogs read it on Save)
"""

from __future__ import annotations

from typing import Optional

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.reactive import reactive
from textual import events as _events
from textual.widget import Widget
from textual.events import Click

from src.tui.widgets.gradient import multi_lerp
from src.theme import palette

# Neutral track/knob shades are intentionally theme-independent.
_OFF_COLOR = "#5a636e"
_TRACK_OFF = "#2d333b"
_TRACK_ON = "#0f3d27"


def _colors() -> dict:
    """Resolve accent-driven colors at render time.

    Rich ``Text`` styles need literal hex values and the active theme can
    change between renders, so these are read per frame, never frozen at
    import time.
    """
    pal = palette()
    return {
        "on_stops": [pal["accent"], pal["accent_2"]],
        "label_on": pal["accent"],
        "label_off": pal["muted"],
        "muted": pal["muted"],
    }


class CyberSwitch(Widget):
    """Animated custom switch: [knob-on-gradient-track] + label row."""

    BINDINGS = [
        Binding("enter", "toggle", "Toggle", show=False),
    ]

    can_focus = True

    value = reactive(False)
    """Logical ON/OFF state of the switch."""

    TRACK_LEN = 5
    ANIM_STEPS = 6
    ANIM_INTERVAL = 0.028  # ~0.17s total animation

    def __init__(
        self,
        label: str,
        description: str = "",
        *,
        switch_key: str = "",
        initial: bool = False,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(id=id, classes=classes)
        self.label = label
        self.description = description
        self.switch_key = switch_key
        self._anim = 1.0 if initial else 0.0
        self._anim_from = self._anim
        self._anim_to = self._anim
        self._anim_i = 0
        self._anim_step = None
        self.add_class("cyber-switch")
        if initial:
            self.add_class("on")
        else:
            self.add_class("off")
        # Assign last so the reactive watcher only animates on later changes.
        self.value = initial

    # ------------------------------------------------------------------ state

    def action_toggle(self) -> None:
        self.toggle()

    def toggle(self) -> None:
        """Flip the logical state (UI triggers the knob animation)."""
        self.value = not self.value

    def set_value(self, on: bool) -> None:
        if on != self.value:
            self.value = on

    def watch_value(self, new_value: bool) -> None:
        if new_value:
            self.add_class("on")
            self.remove_class("off")
        else:
            self.remove_class("on")
            self.add_class("off")
        self._start_anim(new_value)

    # ------------------------------------------------------------- animation

    def _start_anim(self, target: bool) -> None:
        if self._anim_step is not None:
            try:
                self._anim_step.cancel()
            except Exception:
                pass
            self._anim_step = None

        self._anim_from = self._anim
        self._anim_to = 1.0 if target else 0.0
        if abs(self._anim_to - self._anim_from) < 0.01:
            self._anim = self._anim_to
            self.refresh()
            return
        self._anim_i = 0
        try:
            self._anim_step = self.set_interval(self.ANIM_INTERVAL, self._anim_tick)
        except Exception:
            # Fallback (e.g. not mounted yet): jump straight to target.
            self._anim = self._anim_to
            self.refresh()

    def _anim_tick(self) -> None:
        self._anim_i += 1
        t = self._anim_i / self.ANIM_STEPS
        if t >= 1.0:
            self._anim = self._anim_to
            if self._anim_step is not None:
                try:
                    self._anim_step.cancel()
                except Exception:
                    pass
                self._anim_step = None
        else:
            eased = 1.0 - (1.0 - t) ** 2  # ease-out quad
            self._anim = self._anim_from + (self._anim_to - self._anim_from) * eased
        self.refresh()

    # ----------------------------------------------------------------- input

    def on_click(self, event: Click) -> None:
        self.toggle()

    def on_key(self, event: _events.Key) -> None:
        # Space is not bindable as a key-string, so handle it directly.
        if event.key == " ":
            event.stop()
            self.toggle()

    # ---------------------------------------------------------------- render

    def render(self) -> Text:
        cols = _colors()
        on_stops = cols["on_stops"]
        out = Text()
        n = self.TRACK_LEN
        pos = max(0.0, min(1.0, self._anim))
        idx = int(round(pos * (n - 1)))
        on = bool(self.value)

        for i in range(n):
            if i == idx:
                if on:
                    color = multi_lerp(on_stops, pos)
                    out.append("⬤", style=Style(color=color, bold=True))
                else:
                    out.append("⬤", style=Style(color=_OFF_COLOR, bold=True))
            else:
                if on and i < idx:
                    # Trail behind the knob lights up as it slides right
                    color = multi_lerp(on_stops, i / max(1, n - 1))
                    out.append("─", style=Style(color=color, bold=True))
                elif on:
                    out.append("─", style=Style(color=_TRACK_ON))
                else:
                    out.append("─", style=Style(color=_TRACK_OFF))

        state_color = cols["label_on"] if on else _OFF_COLOR
        out.append(" ")
        out.append(f"[{'ON' if on else 'OFF'}]", style=Style(color=state_color, bold=True))
        out.append("  ")
        out.append(self.label, style=Style(color=cols["label_on"] if on else cols["label_off"], bold=on))
        if self.description:
            out.append(f"  ·  {self.description}", style=Style(color=cols["muted"]))
        return out

    DEFAULT_CSS = """
    CyberSwitch {
        height: auto;
        width: 1fr;
        min-height: 1;
        padding: 0 1;
        border: none;
        overflow: hidden;
    }
    CyberSwitch:focus {
        border: round $enh-accent-2;
    }
    CyberSwitch.on {
        background: $enh-row-focus-bg;
    }
    """
