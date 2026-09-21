"""
Enhancify Theme Engine & Registry
Provides multiple handcrafted color themes with live preview palettes and instant switching.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.config import config


@dataclass(frozen=True)
class ThemeInfo:
    id: str
    name: str
    description: str
    accent: str          # card titles, borders, primary text accents
    accent_2: str        # focus borders, secondary accents
    bg: str              # Screen background
    text: str             # Screen foreground
    surface: str          # card / header background
    surface_2: str        # Input + ListView background
    border: str           # card / input border
    btn_bg: str           # Button.btn-primary background
    btn_focus_bg: str     # Button:focus background
    btn_focus_fg: str     # Button:focus foreground
    row_focus_bg: str     # ListItem:focus background
    row_focus_fg: str     # ListItem:focus foreground
    log_bg: str           # #log-viewer background
    log_fg: str           # #log-viewer foreground
    preview_palette: List[str]


STATIC_TOKENS: Dict[str, str] = {
    "muted": "#8b949e",     # secondary/help text
    "danger": "#ff4444",    # errors, delete actions
    "warning": "#ffd700",   # tags, cautions
    "tag": "#d2a8ff",       # custom-source / meta tags
    "on_dark": "#ffffff",   # text on strong accent fills
    "success": "#2ea043",   # confirm/allow actions (e.g. downgrade-conflict Yes)
}


THEMES: List[ThemeInfo] = [
    ThemeInfo(
        id="cyber_green",
        name="Cybernetic Green",
        description="Classic Enhancify emerald green with high-contrast cyber aesthetic",
        accent="#00ff7f",
        accent_2="#00e5ff",
        bg="#0d1117",
        text="#e6edf3",
        surface="#161b22",
        surface_2="#0d1117",
        border="#30363d",
        btn_bg="#0d4429",
        btn_focus_bg="#238636",
        btn_focus_fg="#ffffff",
        row_focus_bg="#0d3826",
        row_focus_fg="#00ff7f",
        log_bg="#05080c",
        log_fg="#a8ffb2",
        preview_palette=["#00ff7f", "#00e5ff", "#161b22", "#0d1117"],
    ),
    ThemeInfo(
        id="cyberpunk_neon",
        name="Cyberpunk Neon",
        description="High-energy electric neon pink, hot magenta, and cyan glow",
        accent="#ff007f",
        accent_2="#00f0ff",
        bg="#0c0817",
        text="#f0f6fc",
        surface="#171126",
        surface_2="#0c0817",
        border="#38225c",
        btn_bg="#4a0028",
        btn_focus_bg="#a30052",
        btn_focus_fg="#ffffff",
        row_focus_bg="#380826",
        row_focus_fg="#00f0ff",
        log_bg="#07040d",
        log_fg="#ff80c0",
        preview_palette=["#ff007f", "#00f0ff", "#171126", "#0c0817"],
    ),
    ThemeInfo(
        id="dracula",
        name="Dracula Vampire",
        description="Classic dark theme with vibrant pastel purple, pink, and green accents",
        accent="#bd93f9",
        accent_2="#ff79c6",
        bg="#1e1f29",
        text="#f8f8f2",
        surface="#282a36",
        surface_2="#1e1f29",
        border="#44475a",
        btn_bg="#382a54",
        btn_focus_bg="#6272a4",
        btn_focus_fg="#ffffff",
        row_focus_bg="#44475a",
        row_focus_fg="#50fa7b",
        log_bg="#15161e",
        log_fg="#50fa7b",
        preview_palette=["#bd93f9", "#ff79c6", "#50fa7b", "#282a36"],
    ),
    ThemeInfo(
        id="catppuccin",
        name="Catppuccin Mocha",
        description="Soothing pastel palette with mauve, sky blue, and sapphire tones",
        accent="#cba6f7",
        accent_2="#89dceb",
        bg="#181825",
        text="#cdd6f4",
        surface="#1e1e2e",
        surface_2="#181825",
        border="#313244",
        btn_bg="#3b2d54",
        btn_focus_bg="#45475a",
        btn_focus_fg="#ffffff",
        row_focus_bg="#313244",
        row_focus_fg="#a6e3a1",
        log_bg="#11111b",
        log_fg="#a6e3a1",
        preview_palette=["#cba6f7", "#89dceb", "#a6e3a1", "#1e1e2e"],
    ),
    ThemeInfo(
        id="nordic_frost",
        name="Nordic Frost",
        description="Arctic-inspired cool frost blues, aurora cyan, and polar night slate",
        accent="#88c0d0",
        accent_2="#81a1c1",
        bg="#242933",
        text="#eceff4",
        surface="#2e3440",
        surface_2="#242933",
        border="#434c5e",
        btn_bg="#2b4554",
        btn_focus_bg="#4c566a",
        btn_focus_fg="#ffffff",
        row_focus_bg="#3b4252",
        row_focus_fg="#88c0d0",
        log_bg="#1b1f27",
        log_fg="#88c0d0",
        preview_palette=["#88c0d0", "#81a1c1", "#a3be8c", "#2e3440"],
    ),
    ThemeInfo(
        id="sunset_amber",
        name="Sunset Amber",
        description="Warm golden amber, blazing sunset orange, and rich dark charcoal",
        accent="#ffb703",
        accent_2="#fb8500",
        bg="#14110e",
        text="#fdf0d5",
        surface="#1f1a15",
        surface_2="#14110e",
        border="#3d3328",
        btn_bg="#4a3400",
        btn_focus_bg="#fb8500",
        btn_focus_fg="#14110e",
        row_focus_bg="#362919",
        row_focus_fg="#ffb703",
        log_bg="#0a0806",
        log_fg="#ffd166",
        preview_palette=["#ffb703", "#fb8500", "#06d6a0", "#1f1a15"],
    ),
    ThemeInfo(
        id="matrix_retro",
        name="Matrix Phosphor",
        description="Pure retro terminal black and lime-green CRT phosphor glow",
        accent="#00ff00",
        accent_2="#39ff14",
        bg="#000000",
        text="#00ff00",
        surface="#041004",
        surface_2="#000000",
        border="#004400",
        btn_bg="#042404",
        btn_focus_bg="#00ff00",
        btn_focus_fg="#000000",
        row_focus_bg="#003300",
        row_focus_fg="#39ff14",
        log_bg="#000000",
        log_fg="#00ff00",
        preview_palette=["#00ff00", "#39ff14", "#041004", "#000000"],
    ),
    ThemeInfo(
        id="oled_midnight",
        name="OLED Midnight Dark",
        description="Deep pitch black with ice blue accents, tuned for battery savings on AMOLED",
        accent="#00a8ff",
        accent_2="#ffffff",
        bg="#000000",
        text="#f0f0f0",
        surface="#0a0a0a",
        surface_2="#000000",
        border="#222222",
        btn_bg="#00283d",
        btn_focus_bg="#00a8ff",
        btn_focus_fg="#000000",
        row_focus_bg="#141414",
        row_focus_fg="#00a8ff",
        log_bg="#000000",
        log_fg="#70cfff",
        preview_palette=["#00a8ff", "#ffffff", "#111111", "#000000"],
    ),
]


THEME_MAP: Dict[str, ThemeInfo] = {t.id: t for t in THEMES}


def get_current_theme() -> ThemeInfo:
    """Read active theme from configuration."""
    theme_id = config.get("THEME_ID", "")
    if theme_id and theme_id in THEME_MAP:
        return THEME_MAP[theme_id]

    # Fallback to GREEN_THEME legacy toggle
    if config.is_on("GREEN_THEME"):
        return THEME_MAP["cyber_green"]
    elif config.is_on("DARK_THEME"):
        return THEME_MAP["oled_midnight"]
    return THEME_MAP["cyber_green"]


def set_current_theme(theme_id: str) -> bool:
    """Save active theme to config."""
    if theme_id not in THEME_MAP:
        return False

    theme = THEME_MAP[theme_id]
    config.set("THEME_ID", theme.id)
    config.set("THEME", theme.name)

    # Maintain legacy toggles
    if theme.id == "cyber_green":
        config.set("GREEN_THEME", "on")
        config.set("DARK_THEME", "off")
    else:
        config.set("GREEN_THEME", "off")
        config.set("DARK_THEME", "on")

    return True


def palette(theme: Optional[ThemeInfo] = None) -> Dict[str, str]:
    """Hex values for the active theme, keyed by token name (no '$enh-' prefix)."""
    t = theme or get_current_theme()
    result = {
        "accent": t.accent,
        "accent_2": t.accent_2,
        "bg": t.bg,
        "text": t.text,
        "surface": t.surface,
        "surface_2": t.surface_2,
        "border": t.border,
        "btn_bg": t.btn_bg,
        "btn_focus_bg": t.btn_focus_bg,
        "btn_focus_fg": t.btn_focus_fg,
        "row_focus_bg": t.row_focus_bg,
        "row_focus_fg": t.row_focus_fg,
        "log_bg": t.log_bg,
        "log_fg": t.log_fg,
    }
    result.update(STATIC_TOKENS)
    return result


def css_variables(theme: Optional[ThemeInfo] = None) -> Dict[str, str]:
    """{'enh-accent': '#00ff7f', ...} for App.get_css_variables()."""
    return {f"enh-{k.replace('_', '-')}": v for k, v in palette(theme).items()}


