"""iPhone hardware finish from lockdownd color keys.

lockdownd exposes up to four root keys (readable via
``ideviceinfo -u <UDID> -k <key>``):

- ``DeviceColor`` / ``DeviceEnclosureColor`` — front bezel / back+frame.
  Format varies by iOS era: ``#3b3b3c``, ``black``, or an integer-as-string
  (``1`` = black iPhone 7, ``8`` = coral XR). Integer meanings are
  per-``ProductType`` — there is no global table.
- ``DeviceRGBColor`` / ``DeviceEnclosureRGBColor`` — integer ``0x00RRGGBB``
  on some iOS versions (decimal or ``0x…`` string from ideviceinfo).

Strategy: prefer the enclosure RGB (exact hex, no table needed), then the
front RGB, then a small curated (ProductType, int) table built only from
sourced observations, then plain named colors (``black``, ``midnight``…).
Anything unrecognized resolves to ``("", "")`` so the UI hides the chip
instead of guessing wrong.
"""

from __future__ import annotations

import re

_HEX_RE = re.compile(r"^#([0-9a-f]{3}|[0-9a-f]{6})$", re.IGNORECASE)

#: Common marketing / lockdown names -> approximate display hex.
NAMED_HEX: dict[str, str] = {
    "black": "#1d1d1f",
    "space black": "#1d1d1f",
    "space gray": "#3b3b3c",
    "space grey": "#3b3b3c",
    # Midnight is a very dark blue, not pure black (blue tinge in person).
    "midnight": "#1e2a38",
    "graphite": "#3b3b3c",
    "white": "#f5f5f7",
    "silver": "#e3e4e6",
    "starlight": "#f5f5f7",
    "cloud white": "#f5f5f7",
    "gold": "#f4e8ce",
    "light gold": "#f4e8ce",
    "natural": "#c2bcb2",
    "natural titanium": "#c2bcb2",
    "desert": "#c2a884",
    "desert titanium": "#c2a884",
    "blue": "#3b4d63",
    "sierra blue": "#a7c1d9",
    "alpine green": "#5e6f5a",
    "green": "#a8dab5",
    "yellow": "#f9e179",
    "pink": "#ecc0c5",
    "purple": "#c8bfe7",
    "deep purple": "#594f63",
    "red": "#c8102e",
    "(product)red": "#c8102e",
    "product red": "#c8102e",
    "coral": "#ff7f6b",
    "teal": "#a9d1c7",
    "ultramarine": "#9ba9d0",
}

#: (ProductType, enclosure/front int) -> (marketing name, hex).
#: Only entries with a sourced observation — never guess. Sources:
#: libimobiledevice#818 (XS Max: 1 Space Gray / 2 Silver / 4 Gold;
#: XR: 1 Black / 2 White / 6 Red / 7 Yellow / 8 Coral / 9 Blue;
#: X: 1 Black / 2 White) and the Apple Community lockdown dump
#: (iPhone9,4 DeviceColor=1 DeviceEnclosureColor=1 = black).
INT_COLORS: dict[tuple[str, int], tuple[str, str]] = {
    ("iPhone7,2", 1): ("Black", "#1d1d1f"),  # iPhone 6 — same 1=black lineage
    ("iPhone9,4", 1): ("Black", "#1d1d1f"),  # 7 Plus lockdown dump
    ("iPhone10,3", 1): ("Space Gray", "#3b3b3c"),  # X
    ("iPhone10,3", 2): ("Silver", "#e3e4e6"),
    ("iPhone10,6", 1): ("Space Gray", "#3b3b3c"),
    ("iPhone10,6", 2): ("Silver", "#e3e4e6"),
    ("iPhone11,2", 1): ("Space Gray", "#3b3b3c"),  # XS
    ("iPhone11,2", 2): ("Silver", "#e3e4e6"),
    ("iPhone11,2", 4): ("Gold", "#f4e8ce"),
    ("iPhone11,6", 1): ("Space Gray", "#3b3b3c"),  # XS Max
    ("iPhone11,6", 2): ("Silver", "#e3e4e6"),
    ("iPhone11,6", 4): ("Gold", "#f4e8ce"),
    ("iPhone11,8", 1): ("Black", "#1d1d1f"),  # XR
    ("iPhone11,8", 2): ("White", "#f5f5f7"),
    ("iPhone11,8", 6): ("(PRODUCT)RED", "#c8102e"),
    ("iPhone11,8", 7): ("Yellow", "#f9e179"),
    ("iPhone11,8", 8): ("Coral", "#ff7f6b"),
    ("iPhone11,8", 9): ("Blue", "#a7c1d9"),
    # iPhone 13 (iPhone14,5): id 1 = Midnight. Evidenced live: a Midnight
    # unit (order prefix MLPF3, sold as "iPhone 13 128GB Midnight") reports
    # DeviceColor=1 DeviceEnclosureColor=1. Midnight is a very dark blue,
    # not pure black. Other ids unverified — absent on purpose so the UI
    # hides instead of guessing.
    ("iPhone14,5", 1): ("Midnight", "#1e2a38"),
}


def _expand_short_hex(hex3: str) -> str:
    return "#" + "".join(c * 2 for c in hex3.lower())


def normalize_hex_color(raw: str) -> str:
    """Normalize any lockdown color value to lowercase ``#rrggbb`` or ``""``.

    Accepts ``#rgb`` / ``#rrggbb``, ``0xRRGGBB`` / decimal RGB ints, and
    plain names (``black``, ``midnight``…). Integer color *ids* (``1``–``9``)
    are NOT RGB and return ``""`` here — they need the ProductType table.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if _HEX_RE.match(s):
        h = s.lower()
        if len(h) == 4:  # #rgb
            return _expand_short_hex(h[1:])
        return h
    lowered = s.lower()
    if lowered in NAMED_HEX:
        return NAMED_HEX[lowered]
    # Strip a marketing prefix users sometimes paste, e.g. "(PRODUCT)RED".
    if lowered.startswith("(") and ")" in lowered:
        short = lowered.split(")", 1)[1].strip()
        if short in NAMED_HEX:
            return NAMED_HEX[short]
    # RGB integer: decimal ("16711680") or hex ("0xFF0000", "ff0000").
    candidate = s
    base = 10
    if candidate.lower().startswith("0x"):
        candidate, base = candidate[2:], 16
    elif re.fullmatch(r"[0-9a-fA-F]{6}", candidate):
        # Bare 6-hex-digit dump — only treat as RGB when it looks like one.
        # Single-digit ids ("1".."9") must NOT become near-black "#000001".
        base = 16
    elif not re.fullmatch(r"\d+", candidate):
        return ""
    try:
        value = int(candidate, base)
    except (TypeError, ValueError):
        return ""
    if value <= 9 or value > 0xFFFFFF or value <= 0:
        # 1..9 are per-model color ids, not RGB (would render near-black).
        return ""
    return f"#{value & 0xFFFFFF:06x}"


def _parse_id(raw: str) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def resolve_device_color(
    product_type: str = "",
    front: str = "",
    enclosure: str = "",
    rgb: str = "",
    enclosure_rgb: str = "",
) -> tuple[str, str]:
    """Resolve lockdown color keys to ``(name, hex)``; ``("", "")`` = unknown.

    Preference: enclosure RGB → front RGB → (ProductType, id) table →
    named color strings. Enclosure (back/frame) is what users recognize as
    "the iPhone color"; the front is usually just black/white bezel.
    """
    product = (product_type or "").strip()
    enclosure_hex = normalize_hex_color(enclosure_rgb)
    if enclosure_hex:
        code = _parse_id(enclosure)
        if code is not None and (product, code) in INT_COLORS:
            return INT_COLORS[(product, code)]
        return ("", enclosure_hex)
    front_hex = normalize_hex_color(rgb)
    if front_hex:
        code = _parse_id(front)
        if code is not None and (product, code) in INT_COLORS:
            return INT_COLORS[(product, code)]
        return ("", front_hex)
    for raw in (enclosure, front):
        if not raw or not str(raw).strip():
            continue
        code = _parse_id(str(raw))
        if code is not None and (product, code) in INT_COLORS:
            return INT_COLORS[(product, code)]
        named = normalize_hex_color(str(raw))
        if named:
            label = str(raw).strip()
            # Title-case plain names for the chip ("midnight" -> "Midnight").
            if label.lower() in NAMED_HEX and len(label) < 24:
                label = label.strip().title()
                if label.lower() == "product red":
                    label = "(PRODUCT)RED"
            else:
                label = ""
            return (label, named)
    return ("", "")
