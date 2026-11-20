#!/usr/bin/env python3
"""Draws the README's high-level workflow diagram as two SVGs (light and dark theme).

    python3 docs/images/make-overview.py

Writes overview-light.svg and overview-dark.svg next to this script. The README shows the one that
matches the reader's GitHub theme through a <picture> element. Edit the text and stages here, not in
the SVGs.
"""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1200, 668
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

THEMES = {
    "light": {
        "frame": "#f6f8fa", "frame_line": "#d0d7de", "card": "#ffffff", "card_line": "#d0d7de",
        "text": "#1f2328", "muted": "#59636e", "line": "#8c959f", "band": "#eef1f4",
        "you_bg": "#fff8c5", "you_line": "#d4a72c", "you_text": "#7d4e00", "tint": 0.12,
        "violet": "#8250df", "blue": "#0969da", "teal": "#0a7d7a", "pink": "#bf3989", "green": "#1a7f37",
    },
    "dark": {
        "frame": "#161b22", "frame_line": "#30363d", "card": "#0d1117", "card_line": "#30363d",
        "text": "#e6edf3", "muted": "#9198a1", "line": "#656c76", "band": "#1c2128",
        "you_bg": "#2e2510", "you_line": "#9e6a03", "you_text": "#e3b341", "tint": 0.22,
        "violet": "#ab7df8", "blue": "#4493f8", "teal": "#39c5bb", "pink": "#db61a2", "green": "#3fb950",
    },
}

# 24x24 stroke icons
ICONS = {
    "idea": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z"/>',
    "ticket": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M15 6v12" stroke-dasharray="2 2"/>',
    "issue": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    "chat": '<path d="M4 5h16v11H10l-5 4v-4H4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "plan": '<path d="M4 6h9M9 12h11M6 18h9" stroke-width="3"/>',
    "code": '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 4.5l-3 15"/>',
    "merge": '<circle cx="6" cy="5" r="2.2"/><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="12" r="2.2"/>'
             '<path d="M6 7.2v9.6M6 7.2c0 4 4.5 4.8 9.8 4.8"/>',
    "docs": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 14l2 2 4-4"/>',
    "person": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "approve": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "next": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8M13 8l4 4-4 4"/>',
}

INPUTS = [("idea", "An idea"), ("ticket", "Jira ticket"), ("issue", "GitHub issue"), ("file", "Spec file")]

STAGES = [
    {"n": 1, "name": "SHAPE", "color": "violet", "icon": "chat", "cmd": "/factory:vision",
     "lines": ["Plays it back,", "asks questions,", "writes the specs"],
     "you": ["Answer, then", "review the specs"]},
    {"n": 2, "name": "PLAN", "color": "blue", "icon": "plan", "cmd": "the planner",
     "lines": ["Plans the whole", "build once, in", "parallel waves"],
     "you": ["Approve the plan;", "tickets get filed"]},
    {"n": 3, "name": "BUILD", "color": "teal", "icon": "code", "cmd": "/factory:run",
     "lines": ["Intake, spec, code,", "checks and reviews", "for every ticket"],
     "you": ["Step in only when", "a job asks for you"]},
    {"n": 4, "name": "MERGE", "color": "pink", "icon": "merge", "cmd": "merge request",
     "lines": ["Ready, with tests,", "docs and a summary", "for your review"],
     "you": ["Review and merge.", "Never automatic."]},
    {"n": 5, "name": "SHIP", "color": "green", "icon": "docs", "cmd": "/factory:docs",
     "lines": ["Checks the drafts", "against the merge,", "then publishes"],
     "you": ["Approve each page", "before it goes out"]},
]

FOOTER = [("shield", "Fenced agents", "Each agent is fenced into its own job"),
          ("approve", "Your approval first", "Every Jira write waits for your OK"),
          ("next", "Always a next step", "Each step ends with what comes next")]

CARD_X, CARD_W, GAP, CARD_Y, CARD_H = 200, 172, 22, 116, 350
ICON_Y = 168


def icon(name, cx, cy, size, color):
    s = size / 24
    return (f'<g transform="translate({cx - size / 2:.1f} {cy - size / 2:.1f}) scale({s:.3f})" fill="none" '
            f'stroke="{color}" color="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'{ICONS[name]}</g>')


def text(x, y, s, size, fill, weight=400, anchor="start", family=SANS, extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def draw(t):
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
         f'aria-labelledby="title desc">',
         '<title id="title">The software factory, from idea to merged code</title>',
         '<desc id="desc">Start from an idea, a Jira ticket, a GitHub issue or a spec file. Five stages: shape '
         'with /factory:vision, plan with the planner, build with /factory:run, merge, and ship documentation '
         'with /factory:docs. You answer, approve and merge; the next run sees each merge and starts the next '
         'wave.</desc>',
         f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="22" fill="{t["frame"]}" '
         f'stroke="{t["frame_line"]}"/>']
    o.append(text(44, 62, "From idea to merged code", 26, t["text"], 700))
    o.append(text(44, 90, "You make the decisions. Claude agents plan, build, check and document. "
                          "Nothing merges without you.", 15.5, t["muted"]))
    o.append(f'<rect x="884" y="49" width="14" height="14" rx="4" fill="{t["you_bg"]}" stroke="{t["you_line"]}"/>')
    o.append(text(905, 61, "You decide", 14, t["muted"]))
    o.append(f'<rect x="1004" y="49" width="14" height="14" rx="4" fill="{t["card"]}" stroke="{t["blue"]}"/>')
    o.append(text(1025, 61, "The factory works", 14, t["muted"]))

    # where work starts
    o.append(text(40, 138, "START FROM", 12, t["muted"], 700, extra=' letter-spacing="1.2"'))
    centers = []
    for i, (ic, label) in enumerate(INPUTS):
        y = 150 + i * 56
        centers.append(y + 22)
        o.append(f'<rect x="40" y="{y}" width="136" height="44" rx="12" fill="{t["card"]}" stroke="{t["card_line"]}"/>')
        o.append(icon(ic, 61, y + 22, 20, t["muted"]))
        o.append(text(80, y + 27, label, 14.5, t["text"], 500))
        o.append(f'<path d="M176 {y + 22}H188" stroke="{t["line"]}" stroke-width="1.5" fill="none"/>')
    mid = (centers[0] + centers[-1]) / 2
    o.append(f'<path d="M188 {centers[0]}V{centers[-1]}M188 {mid}H194" stroke="{t["line"]}" stroke-width="1.5" '
             f'fill="none" stroke-linecap="round"/>')
    o.append(f'<path d="M192 {mid - 5}L198 {mid}L192 {mid + 5}z" fill="{t["line"]}"/>')

    # the pipeline line behind the cards, with an arrowhead in each gap
    xs = [CARD_X + i * (CARD_W + GAP) for i in range(len(STAGES))]
    o.append(f'<path d="M{xs[0] + CARD_W / 2} {ICON_Y}H{xs[-1] + CARD_W / 2}" stroke="{t["line"]}" '
             f'stroke-width="1.5"/>')
    for x in xs[1:]:
        o.append(f'<path d="M{x - 9} {ICON_Y - 5}L{x - 2} {ICON_Y}L{x - 9} {ICON_Y + 5}z" fill="{t["line"]}"/>')

    for x, s in zip(xs, STAGES):
        c, cx = t[s["color"]], x + CARD_W / 2
        o.append(f'<rect x="{x}" y="{CARD_Y}" width="{CARD_W}" height="{CARD_H}" rx="16" fill="{t["card"]}" '
                 f'stroke="{t["card_line"]}"/>')
        o.append(f'<clipPath id="card{s["n"]}"><rect x="{x}" y="{CARD_Y}" width="{CARD_W}" height="{CARD_H}" '
                 f'rx="16"/></clipPath>')
        o.append(f'<rect x="{x}" y="{CARD_Y}" width="{CARD_W}" height="5" fill="{c}" clip-path="url(#card{s["n"]})"/>')
        o.append(f'<circle cx="{cx}" cy="{ICON_Y}" r="28" fill="{c}" fill-opacity="{t["tint"]}"/>')
        o.append(icon(s["icon"], cx, ICON_Y, 28, c))
        o.append(text(cx, 226, f'{s["n"]} · {s["name"]}', 12.5, c, 700, "middle", extra=' letter-spacing="1.3"'))
        o.append(text(cx, 250, s["cmd"], 14, t["text"], 600, "middle", MONO))
        for k, line in enumerate(s["lines"]):
            o.append(text(cx, 283 + k * 21, line, 15, t["muted"], 400, "middle"))
        px, py = x + 10, 362
        o.append(f'<rect x="{px}" y="{py}" width="{CARD_W - 20}" height="86" rx="12" fill="{t["you_bg"]}" '
                 f'stroke="{t["you_line"]}"/>')
        o.append(icon("person", px + 21, py + 18, 16, t["you_text"]))
        o.append(text(px + 35, py + 23, "YOU", 12, t["you_text"], 700, extra=' letter-spacing="1.2"'))
        for k, line in enumerate(s["you"]):
            o.append(text(px + 12, py + 47 + k * 20, line, 14, t["text"], 500))

    # after a merge, the next run picks up the next wave
    b, m = xs[2] + CARD_W / 2, xs[3] + CARD_W / 2
    bottom = CARD_Y + CARD_H
    o.append(f'<path d="M{m} {bottom}V{bottom + 28}H{b}V{bottom + 8}" stroke="{t["line"]}" stroke-width="1.5" '
             f'fill="none" stroke-dasharray="5 4"/>')
    o.append(f'<path d="M{b - 5} {bottom + 9}L{b} {bottom + 2}L{b + 5} {bottom + 9}z" fill="{t["line"]}"/>')
    o.append(text((b + m) / 2, bottom + 50, "The next run sees the merge and starts the next wave", 13.5,
                  t["muted"], 400, "middle", extra=' font-style="italic"'))

    # how it stays safe and guided
    o.append(f'<rect x="36" y="544" width="{W - 72}" height="92" rx="16" fill="{t["band"]}"/>')
    for i, (ic, title, desc) in enumerate(FOOTER):
        x0 = 64 + i * 376
        o.append(f'<circle cx="{x0 + 20}" cy="590" r="21" fill="{t["card"]}" stroke="{t["card_line"]}"/>')
        o.append(icon(ic, x0 + 20, 590, 22, t["text"]))
        o.append(text(x0 + 54, 584, title, 15, t["text"], 700))
        o.append(text(x0 + 54, 606, desc, 13.5, t["muted"]))
    o.append("</svg>")
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    for name, theme in THEMES.items():
        (here / f"overview-{name}.svg").write_text(draw(theme))
        print(f"wrote {here / f'overview-{name}.svg'}")
