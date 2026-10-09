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
    muted: str            # secondary/help text; >=7:1 contrast on surface, surface_2, bg
    preview_palette: List[str]


STATIC_TOKENS: Dict[str, str] = {
    "danger": "#ff4444",    # errors, delete actions
    "warning": "#ffd700",   # tags, cautions
    "tag": "#d2a8ff",       # custom-source / meta tags
    "on_dark": "#ffffff",   # text on strong accent fills
    "success": "#2ea043",   # confirm/allow actions (e.g. downgrade-conflict Yes)
}


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of a '#rrggbb' color."""
    h = hex_color.lstrip("#")
    lin = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        lin.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two '#rrggbb' colors."""
    la, lb = relative_luminance(a), relative_luminance(b)
    light, dark = (la, lb) if la >= lb else (lb, la)
    return (light + 0.05) / (dark + 0.05)


def blend_hex(a: str, b: str, t: float) -> str:
    """Linear RGB mix of two '#rrggbb' colors; t=0 -> a, t=1 -> b."""
    ha, hb = a.lstrip("#"), b.lstrip("#")
    out = "#"
    for i in (0, 2, 4):
        ca, cb = int(ha[i:i + 2], 16), int(hb[i:i + 2], 16)
        out += f"{round(ca + (cb - ca) * t):02x}"
    return out


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
        muted="#acb2b8",
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
        muted="#afb1bc",
        preview_palette=["#ff007f", "#00f0ff", "#171126", "#0c0817"],
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
        muted="#bab09b",
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
        muted="#01cd01",
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
        muted="#b0b0b0",
        preview_palette=["#00a8ff", "#ffffff", "#111111", "#000000"],
    ),
    ThemeInfo(
        id="kanagawa_dragon",
        name="Kanagawa Dragon",
        description="Ink-wash charcoal with autumn gold, dragon red, and wave blue",
        accent="#e6c384",
        accent_2="#7fb4ca",
        bg="#181616",
        text="#c5c9c5",
        surface="#282727",
        surface_2="#181616",
        border="#393836",
        btn_bg="#3a3220",
        btn_focus_bg="#c4b28a",
        btn_focus_fg="#181616",
        row_focus_bg="#2d4f67",
        row_focus_fg="#e6c384",
        log_bg="#0d0c0c",
        log_fg="#87a987",
        muted="#b1b4b0",
        preview_palette=["#e6c384", "#7fb4ca", "#c4746e", "#282727"],
    ),
    ThemeInfo(
        id="gotham",
        name="Gotham",
        description="Dark city-night teal and cyan on deep navy black",
        accent="#2aa889",
        accent_2="#33859e",
        bg="#0c1014",
        text="#99d1ce",
        surface="#11151c",
        surface_2="#0c1014",
        border="#0a3749",
        btn_bg="#0a3749",
        btn_focus_bg="#245361",
        btn_focus_fg="#d3ebe9",
        row_focus_bg="#0a3749",
        row_focus_fg="#99d1ce",
        log_bg="#080c10",
        log_fg="#2aa889",
        muted="#89bab9",
        preview_palette=["#2aa889", "#33859e", "#edb443", "#11151c"],
    ),
    ThemeInfo(
        id="moonfly",
        name="Moonfly",
        description="Pure-black night sky with soft blue and violet glow",
        accent="#80a0ff",
        accent_2="#cf87e8",
        bg="#080808",
        text="#bdbdbd",
        surface="#1c1c1c",
        surface_2="#080808",
        border="#323437",
        btn_bg="#1c2a4d",
        btn_focus_bg="#80a0ff",
        btn_focus_fg="#080808",
        row_focus_bg="#262626",
        row_focus_fg="#80a0ff",
        log_bg="#000000",
        log_fg="#8cc85f",
        muted="#b0b0b0",
        preview_palette=["#80a0ff", "#cf87e8", "#8cc85f", "#1c1c1c"],
    ),
    ThemeInfo(
        id="jellybeans",
        name="Jellybeans",
        description="Warm candy-colored orange, sky blue, and sage on charcoal",
        accent="#ffba7b",
        accent_2="#97bedc",
        bg="#121212",
        text="#dedede",
        surface="#1c1c1c",
        surface_2="#121212",
        border="#3a3a3a",
        btn_bg="#3d2a14",
        btn_focus_bg="#ffa560",
        btn_focus_fg="#121212",
        row_focus_bg="#474e91",
        row_focus_fg="#f4f4f4",
        log_bg="#0c0c0c",
        log_fg="#94b979",
        muted="#b1b1b1",
        preview_palette=["#ffba7b", "#97bedc", "#94b979", "#1c1c1c"],
    ),
    ThemeInfo(
        id="tokyo_night",
        name="Tokyo Night",
        description="Neon-lit Tokyo night blues and violets on deep indigo",
        accent="#7aa2f7",
        accent_2="#bb9af7",
        bg="#1a1b26",
        text="#c0caf5",
        surface="#24283b",
        surface_2="#1a1b26",
        border="#414868",
        btn_bg="#283457",
        btn_focus_bg="#7aa2f7",
        btn_focus_fg="#1a1b26",
        row_focus_bg="#283457",
        row_focus_fg="#7dcfff",
        log_bg="#15161e",
        log_fg="#9ece6a",
        muted="#aab3db",
        preview_palette=["#7aa2f7", "#bb9af7", "#9ece6a", "#24283b"],
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
        "muted": t.muted,
    }
    result.update(STATIC_TOKENS)
    return result


def css_variables(theme: Optional[ThemeInfo] = None) -> Dict[str, str]:
    """{'enh-accent': '#00ff7f', ...} for App.get_css_variables()."""
    return {f"enh-{k.replace('_', '-')}": v for k, v in palette(theme).items()}


