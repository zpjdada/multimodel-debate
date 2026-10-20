#!/usr/bin/env python3
"""Generate assets/cover.svg and assets/cover-titled.svg.

One scene: a round table seen from slightly above. Five robot seats sit behind
it — left to right: one reading a document with a search lens, one thinking, the
centre one making the case under the spotlight, one thinking, one raising a vote
token. Two more sit in front of the table with their backs to the camera,
cropped by the frame.

The scene carries the idea; only the second file has a title lockup.

Run: python assets/make-cover.py
Then rasterise the two SVG files at 1280x640, e.g. headless Chrome:
  chrome --headless=new --hide-scrollbars --force-device-scale-factor=2 \
         --window-size=1280,640 --screenshot=cover.png assets/cover.svg
The committed PNGs were made that way and then resized to 1280x640.
"""
from pathlib import Path

W, H = 1280, 640
TEAL, BLUE, VIOLET, AMBER = "#3ddc97", "#4aa3ff", "#b07dff", "#ffb86b"
RIM = "#27455e"

# Table geometry, shared by the seats and the rim so they line up.
TX, TY, TRX, TRY = 640, 505, 555, 105

OUT = Path(__file__).resolve().parent


def rim_y(x: float) -> float:
    """Height of the table's far rim at x — the line every seat is cut by."""
    dx = min(1.0, abs(x - TX) / TRX)
    return TY - TRY * (1.0 - dx * dx) ** 0.5


def blur(name: str, sd: float) -> str:
    return (
        f'<filter id="{name}" x="-90%" y="-90%" width="280%" height="280%">'
        f'<feGaussianBlur stdDeviation="{sd}"/></filter>'
    )


DEFS = f"""<defs>
  <radialGradient id="sky" cx="50%" cy="26%" r="82%">
    <stop offset="0" stop-color="#123f5c"/>
    <stop offset="0.30" stop-color="#091b2a"/>
    <stop offset="1" stop-color="#03060a"/>
  </radialGradient>
  <radialGradient id="halo" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="{TEAL}" stop-opacity="0.22"/>
    <stop offset="0.42" stop-color="{TEAL}" stop-opacity="0.08"/>
    <stop offset="1" stop-color="{TEAL}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="haloBlue" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="{BLUE}" stop-opacity="0.10"/>
    <stop offset="1" stop-color="{BLUE}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="vig" cx="50%" cy="42%" r="74%">
    <stop offset="0.40" stop-color="#03060a" stop-opacity="0"/>
    <stop offset="1" stop-color="#03060a" stop-opacity="0.90"/>
  </radialGradient>
  <linearGradient id="torso" x1="0.2" y1="0" x2="0.8" y2="1">
    <stop offset="0" stop-color="#1e3549"/>
    <stop offset="0.34" stop-color="#112130"/>
    <stop offset="1" stop-color="#060c14"/>
  </linearGradient>
  <linearGradient id="headFill" x1="0.2" y1="0" x2="0.8" y2="1">
    <stop offset="0" stop-color="#1d3448"/>
    <stop offset="0.45" stop-color="#0f1e2b"/>
    <stop offset="1" stop-color="#080f18"/>
  </linearGradient>
  <radialGradient id="tableTop" cx="50%" cy="44%" r="62%">
    <stop offset="0" stop-color="#16405c"/>
    <stop offset="0.48" stop-color="#0c2436"/>
    <stop offset="0.84" stop-color="#071624"/>
    <stop offset="1" stop-color="#040d17"/>
  </radialGradient>
  <linearGradient id="edge" x1="0.5" y1="0" x2="0.5" y2="1">
    <stop offset="0" stop-color="#0a1926"/>
    <stop offset="1" stop-color="#02070c"/>
  </linearGradient>
  <linearGradient id="cone" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#d3ecff" stop-opacity="0.12"/>
    <stop offset="0.55" stop-color="#d3ecff" stop-opacity="0.04"/>
    <stop offset="1" stop-color="#d3ecff" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="glass" x1="0" y1="0" x2="0.55" y2="1">
    <stop offset="0" stop-color="#9bdcff" stop-opacity="0.18"/>
    <stop offset="1" stop-color="#9bdcff" stop-opacity="0.03"/>
  </linearGradient>
  <linearGradient id="rimFade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#8fd2ff" stop-opacity="0"/>
    <stop offset="0.28" stop-color="#8fd2ff" stop-opacity="0.45"/>
    <stop offset="0.5" stop-color="#cdeeff" stop-opacity="0.85"/>
    <stop offset="0.72" stop-color="#8fd2ff" stop-opacity="0.45"/>
    <stop offset="1" stop-color="#8fd2ff" stop-opacity="0"/>
  </linearGradient>
  {blur('b4', 4)}{blur('b9', 9)}{blur('b16', 16)}</defs>"""


def glow(color: str, cx: float, cy: float, r: float, op: float, sd: str = "b4") -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" opacity="{op}" filter="url(#{sd})"/>'


def arm(d: str, color: str) -> str:
    return (
        f'<path d="{d}" fill="none" stroke="#070f17" stroke-width="18" stroke-linecap="round"/>'
        f'<path d="{d}" fill="none" stroke="#22405a" stroke-width="10.5" stroke-linecap="round"/>'
        f'<path d="{d}" fill="none" stroke="{color}" stroke-opacity="0.38" stroke-width="3.2" '
        f'stroke-linecap="round" transform="translate(-2.5 -3.5)"/>'
    )


def hand(x: float, y: float, color: str, r: float = 11.5) -> str:
    return (
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="#0a1520" stroke="{color}" '
        f'stroke-opacity="0.7" stroke-width="1.8"/>'
        f'<circle cx="{x}" cy="{y}" r="{r * 0.42:.1f}" fill="{color}" opacity="0.55"/>'
    )


def robot(color: str, tilt: float = 0.0, arm_l: str = "", arm_r: str = "",
          hands: str = "", extra: str = "") -> str:
    """A seat facing the camera. Origin sits at the top centre of the torso."""
    return f"""<g>
    <!-- torso -->
    <path d="M -60 70 C -60 48 -36 41 0 41 C 36 41 60 48 60 70 L 52 230 L -52 230 Z"
          fill="url(#torso)" stroke="#1e3a52" stroke-width="1.1"/>
    <path d="M -60 70 C -60 48 -36 41 0 41" fill="none" stroke="{color}"
          stroke-opacity="0.9" stroke-width="2.6"/>
    <path d="M 60 70 C 60 48 36 41 0 41" fill="none" stroke="#3d6683"
          stroke-opacity="0.7" stroke-width="1.4"/>
    <path d="M -52 230 L -60 70" stroke="#091520" stroke-opacity="0.9" stroke-width="3"/>
    <!-- collar, chest plate, vents -->
    <path d="M -34 52 L 34 52 L 27 72 L -27 72 Z" fill="#081320" stroke="#1b3145" stroke-width="1"/>
    <rect x="-15" y="79" width="30" height="28" rx="7" fill="#050d15" stroke="#16283a"/>
    <path d="M -7 86 L 7 86 M -7 93 L 7 93 M -7 100 L 7 100" stroke="{color}"
          stroke-opacity="0.7" stroke-width="1.8" stroke-linecap="round"/>
    {glow(color, 0, 93, 24, 0.22, 'b9')}
    {arm_l}{arm_r}
    <g transform="rotate({tilt})">
      <rect x="-12" y="18" width="24" height="28" rx="8" fill="#071019" stroke="#152838"/>
      <rect x="-33" y="-38" width="66" height="66" rx="22" fill="url(#headFill)"
            stroke="{RIM}" stroke-width="1.4"/>
      <rect x="-25" y="-28" width="50" height="32" rx="14" fill="#01050a"/>
      <rect x="-17" y="-19" width="12" height="8" rx="4" fill="{color}"/>
      <rect x="5" y="-19" width="12" height="8" rx="4" fill="{color}"/>
      <g filter="url(#b4)" opacity="0.9">
        <rect x="-19" y="-22" width="15" height="14" rx="6" fill="{color}"/>
        <rect x="4" y="-22" width="15" height="14" rx="6" fill="{color}"/>
      </g>
      <rect x="-41" y="-16" width="8" height="27" rx="3.5" fill="#152838" stroke="#204055"/>
      <rect x="33" y="-16" width="8" height="27" rx="3.5" fill="#152838" stroke="#204055"/>
      <path d="M -33 -33 C -23 -41 -7 -42 3 -41" fill="none" stroke="#63a0c2"
            stroke-opacity="0.45" stroke-width="1.6"/>
      <path d="M 0 -38 L 0 -55" stroke="{RIM}" stroke-width="2.2"/>
      <circle cx="0" cy="-58" r="3.8" fill="{color}"/>
      {glow(color, 0, -58, 13, 0.5)}
    </g>
    {hands}
    {extra}
  </g>"""


def doc_extra(color: str) -> str:
    """A document held up, with a search lens over it."""
    return f"""<g transform="translate(40 -126) rotate(-8)">
      <rect x="0" y="0" width="82" height="98" rx="8" fill="url(#glass)"
            stroke="{color}" stroke-opacity="0.6" stroke-width="1.4"/>
      <rect x="12" y="15" width="36" height="4" rx="2" fill="{color}" opacity="0.9"/>
      <rect x="12" y="29" width="54" height="3" rx="1.5" fill="#9bdcff" opacity="0.4"/>
      <rect x="12" y="39" width="44" height="3" rx="1.5" fill="#9bdcff" opacity="0.4"/>
      <rect x="12" y="49" width="50" height="3" rx="1.5" fill="#9bdcff" opacity="0.28"/>
      <circle cx="48" cy="74" r="12" fill="none" stroke="{color}" stroke-width="2.6" opacity="0.95"/>
      <path d="M 56 82 L 67 93" stroke="{color}" stroke-width="3.2" stroke-linecap="round"/>
      {glow(color, 48, 74, 24, 0.2, 'b9')}
    </g>"""


def thought(color: str, flip: bool = False) -> str:
    s = -1 if flip else 1
    return (
        glow(color, 86 * s, -100, 20, 0.16, "b9")
        + f'<circle cx="{50 * s}" cy="-56" r="3.2" fill="{color}" opacity="0.5"/>'
        + f'<circle cx="{65 * s}" cy="-76" r="5" fill="{color}" opacity="0.45"/>'
        + f'<circle cx="{85 * s}" cy="-101" r="7.6" fill="none" stroke="{color}" '
          f'stroke-opacity="0.65" stroke-width="1.8"/>'
        + f'<circle cx="{85 * s}" cy="-101" r="3.2" fill="{color}" opacity="0.4"/>'
    )


def speech(color: str) -> str:
    """Speech bubble up and right of the speaker, tail angled back onto its head."""
    return f"""<g transform="translate(46 -190)">
      <path d="M 22 94 L -34 158 L 52 94 Z" fill="#0b2133" stroke="{color}"
            stroke-opacity="0.35" stroke-width="1"/>
      <rect x="0" y="0" width="198" height="96" rx="26" fill="url(#glass)"
            stroke="{color}" stroke-opacity="0.45" stroke-width="1.3"/>
      <rect x="26" y="27" width="106" height="4.5" rx="2.2" fill="{color}" opacity="0.85"/>
      <rect x="26" y="43" width="144" height="4" rx="2" fill="#9bdcff" opacity="0.36"/>
      <rect x="26" y="57" width="118" height="4" rx="2" fill="#9bdcff" opacity="0.3"/>
      <rect x="26" y="71" width="62" height="4" rx="2" fill="{color}" opacity="0.4"/>
      {glow(color, 158, 22, 50, 0.12, 'b16')}
    </g>"""


def tally(color: str) -> str:
    return f"""<g transform="translate(96 -104)">
      <rect x="0" y="0" width="86" height="50" rx="17" fill="url(#glass)"
            stroke="{color}" stroke-opacity="0.3"/>
      <circle cx="25" cy="25" r="4.4" fill="{color}" opacity="0.8"/>
      <circle cx="44" cy="25" r="4.4" fill="{color}" opacity="0.5"/>
      <circle cx="63" cy="25" r="4.4" fill="{color}" opacity="0.3"/>
    </g>"""


def token(color: str) -> str:
    """The raised vote token, held above the shoulder."""
    return (
        glow(color, 66, -18, 24, 0.28, "b9")
        + f'<circle cx="66" cy="-18" r="13" fill="#0c1e2b" stroke="{color}" '
          f'stroke-opacity="0.85" stroke-width="1.8"/>'
        + f'<path d="M 59.5 -20 L 64 -13.5 L 73.5 -27" fill="none" stroke="{color}" '
          f'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def scene(titled: bool) -> str:
    title = ""
    if titled:
        title = """<g>
      <text x="74" y="94" font-family="'Noto Sans SC','Microsoft YaHei','PingFang SC',sans-serif"
            font-size="44" font-weight="700" fill="#f4fcff" letter-spacing="1">Agent 赛博辩论会</text>
      <text x="76" y="124" font-family="ui-monospace, Consolas, monospace" font-size="12"
            letter-spacing="3.8" fill="#7fa2bb">MULTI-SEAT RESEARCH DEBATE</text>
      <path d="M 76 138 L 360 138" stroke="#25415a" stroke-width="1"/>
    </g>"""

    # (x, y, scale, colour, head tilt, left arm, right arm, hands, overlay)
    seats = [
        (218, 300, 0.95, BLUE, -3,
         "M -56 74 C -70 96 -76 122 -78 160",
         "M 56 72 C 74 60 84 30 78 2",
         hand(-78, 168, BLUE) + hand(78, -8, BLUE), doc_extra(BLUE)),
        (424, 268, 0.90, VIOLET, 7,
         "M -56 74 C -68 94 -74 120 -76 158",
         "M 54 80 C 78 84 72 44 36 30",
         hand(-76, 166, VIOLET) + hand(32, 27, VIOLET), thought(VIOLET)),
        (640, 250, 0.92, TEAL, -4,
         "M -56 72 C -86 68 -104 44 -102 12",
         "M 56 70 C 74 44 82 14 84 -18",
         hand(-102, 4, TEAL, 12) + hand(84, -26, TEAL, 12), speech(TEAL)),
        (856, 268, 0.90, VIOLET, -8,
         "M -54 80 C -78 84 -72 44 -36 30",
         "M 56 74 C 68 94 74 120 76 158",
         hand(-32, 27, VIOLET) + hand(76, 166, VIOLET), thought(VIOLET, flip=True)),
        (1062, 300, 0.95, AMBER, -4,
         "M -56 74 C -68 92 -74 118 -76 158",
         "M 56 70 C 66 44 68 14 66 -10",
         hand(-76, 166, AMBER) + hand(66, -20, AMBER), token(AMBER) + tally(AMBER)),
    ]

    far = "".join(
        f'<g transform="translate({x} {y}) scale({s})">'
        + robot(color, tilt, arm(al, color), arm(ar, color), hd, extra) + "</g>"
        for x, y, s, color, tilt, al, ar, hd, extra in seats
    )

    # coloured pool of light on the table in front of each seat
    pools = "".join(
        f'<ellipse cx="{x}" cy="{rim_y(x) + 46}" rx="{70 * s:.0f}" ry="15" '
        f'fill="{color}" opacity="0.16" filter="url(#b9)"/>'
        for x, y, s, color, *_ in seats
    )

    dots = [
        (96, 236, 1.6, 0.26), (168, 110, 1.2, 0.2), (300, 60, 1.8, 0.16),
        (352, 250, 1.1, 0.24), (498, 82, 1.4, 0.18), (548, 172, 1.0, 0.26),
        (712, 58, 1.5, 0.16), (392, 300, 1.2, 0.14), (916, 78, 1.7, 0.18),
        (986, 214, 1.1, 0.24), (1164, 138, 1.5, 0.16), (1222, 272, 1.2, 0.2),
        (64, 430, 1.2, 0.18), (1214, 412, 1.3, 0.16),
    ]
    particles = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#9bdcff" opacity="{op}"/>'
        for cx, cy, r, op in dots
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
     viewBox="0 0 {W} {H}">
{DEFS}
  <rect width="{W}" height="{H}" fill="#03060a"/>
  <rect width="{W}" height="{H}" fill="url(#sky)"/>

  <!-- back wall -->
  <g stroke="#17364e" stroke-width="1" opacity="0.34">
    <path d="M 0 452 H 1280"/>
    <path d="M 0 104 H 1280" opacity="0.28"/>
  </g>

  <ellipse cx="640" cy="292" rx="330" ry="200" fill="url(#halo)"/>
  <ellipse cx="196" cy="330" rx="200" ry="160" fill="url(#haloBlue)"/>
  <ellipse cx="1084" cy="330" rx="200" ry="160" fill="url(#haloBlue)" opacity="0.7"/>
  <path d="M 588 -40 L 692 -40 L 762 470 L 518 470 Z" fill="url(#cone)" filter="url(#b9)"
        opacity="0.65"/>
  {particles}

  {far}

  <!-- round table: shadow, thickness, top, rim -->
  <ellipse cx="{TX}" cy="{TY + 62}" rx="{TRX - 8}" ry="{TRY - 10}" fill="#02060a" opacity="0.85"
           filter="url(#b16)"/>
  <ellipse cx="{TX}" cy="{TY + 20}" rx="{TRX}" ry="{TRY}" fill="url(#edge)" stroke="#0d2130"
           stroke-width="1.2"/>
  <ellipse cx="{TX}" cy="{TY}" rx="{TRX}" ry="{TRY}" fill="url(#tableTop)" stroke="#264a66"
           stroke-width="1.6"/>
  <g stroke="#122636" stroke-width="1" fill="none" opacity="0.75">
    <ellipse cx="{TX}" cy="{TY}" rx="{TRX - 58}" ry="{TRY - 11}"/>
    <ellipse cx="{TX}" cy="{TY}" rx="{TRX - 118}" ry="{TRY - 22}"/>
    <ellipse cx="{TX}" cy="{TY}" rx="{TRX - 186}" ry="{TRY - 35}"/>
  </g>
  <path d="M {TX - TRX + 6} {TY} A {TRX} {TRY} 0 0 1 {TX + TRX - 6} {TY}" fill="none"
        stroke="url(#rimFade)" stroke-width="2.6"/>
  {pools}
  <ellipse cx="{TX}" cy="{TY + 8}" rx="170" ry="44" fill="{TEAL}" opacity="0.07"
           filter="url(#b16)"/>

  <!-- a holographic agenda sheet floating over the table -->
  <g transform="translate(640 452) rotate(-2)" opacity="0.55">
    <rect x="-104" y="-46" width="208" height="92" rx="12" fill="url(#glass)"
          stroke="{TEAL}" stroke-opacity="0.3" stroke-width="1.2"/>
    <rect x="-84" y="-28" width="66" height="5" rx="2.5" fill="{TEAL}" opacity="0.8"/>
    <rect x="-84" y="-11" width="150" height="4" rx="2" fill="#9bdcff" opacity="0.32"/>
    <rect x="-84" y="2" width="126" height="4" rx="2" fill="#9bdcff" opacity="0.26"/>
    <rect x="-84" y="15" width="92" height="4" rx="2" fill="#9bdcff" opacity="0.2"/>
    <rect x="-84" y="28" width="40" height="9" rx="4.5" fill="{TEAL}" opacity="0.28"/>
  </g>

  <!-- foreground: the near rim runs out of frame, leaving the viewer's place empty -->
  <g opacity="0.9">
    <ellipse cx="640" cy="652" rx="300" ry="26" fill="#08131d"/>
  </g>

  <rect width="{W}" height="{H}" fill="url(#vig)"/>
  {title}
</svg>
"""


def main() -> None:
    for name, titled in (("cover.svg", False), ("cover-titled.svg", True)):
        path = OUT / name
        svg = scene(titled)
        # f-string placeholders that expand to nothing leave whitespace-only
        # lines behind; trim so `git diff --check` stays quiet.
        text = "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
