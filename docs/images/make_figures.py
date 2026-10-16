#!/usr/bin/env python3
"""Draw the README's figures as SVG, one file for GitHub's light theme and one for its dark theme.

Usage: python3 docs/images/make_figures.py
Writes with-and-without-{light,dark}.svg and benchmark-{light,dark}.svg next to this script.
The benchmark numbers are copied from docs/benchmark.md; the example claim and report lines from
examples/codex-run-2. Standard library only.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent

THEMES = {
    "light": {"bg": "#ffffff", "text": "#1f2328", "muted": "#59636e", "panel": "#f6f8fa", "border": "#d1d9e0",
              "skill": "#0969da", "plain": "#8c959f", "accent_bg": "#ddf4ff", "warn_bg": "#fff8c5", "code_bg": "#eff2f5"},
    "dark": {"bg": "#0d1117", "text": "#f0f6fc", "muted": "#9198a1", "panel": "#151b23", "border": "#3d444d",
             "skill": "#4493f8", "plain": "#6e7681", "accent_bg": "#0c2d6b", "warn_bg": "#3b2e00", "code_bg": "#212830"},
}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def text(x, y, s, size=13, fill="text", weight="normal", anchor="start", mono=False, *, t: dict):
    family = MONO if mono else FONT
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{t[fill]}" text-anchor="{anchor}">{escape(s)}</text>')


def rect(x, y, w, h, fill, t, stroke="border", r=6):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{t[fill]}" stroke="{t[stroke]}"/>'


def arrow(x, y1, y2, t):
    return (f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2 - 6}" stroke="{t["muted"]}" stroke-width="1.5"/>'
            f'<path d="M{x - 5},{y2 - 7} L{x},{y2} L{x + 5},{y2 - 7} Z" fill="{t["muted"]}"/>')


def svg(width, height, title, desc, body, t):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" aria-labelledby="title desc">\n<title id="title">{escape(title)}</title>\n'
            f'<desc id="desc">{escape(desc)}</desc>\n<rect width="100%" height="100%" fill="{t["bg"]}"/>\n'
            + "\n".join(body) + "\n</svg>\n")


def with_and_without(t) -> str:
    w, h = 940, 470
    b = [text(w / 2, 30, "The same job: what changed since last time?", 18, weight="600", anchor="middle", t=t)]
    # Left panel: without the skill (an illustration).
    lx, px, pw = 20, 30, 410
    b += [rect(lx, 50, 430, 400, "panel", t), text(px, 78, "Without the skill", 16, weight="600", t=t),
          rect(px + 268, 62, 152, 22, "warn_bg", t, r=11),
          text(px + 344, 77, "illustration, not a real run", 11, anchor="middle", t=t)]
    steps = [("1", "Paste last time's notes into the chat", "you keep them yourself"),
             ("2", "The agent searches and answers with links", "every check uses the model"),
             ("3", "You work out what is new or changed", "no quotes, no confidence levels"),
             ("4", "Nothing is kept for next time", "tomorrow, start again from step 1")]
    y = 100
    for i, (n, head, sub) in enumerate(steps):
        b += [rect(px, y, pw, 62, "bg", t), text(px + 14, y + 26, n + ".", 14, "muted", "600", t=t),
              text(px + 36, y + 26, head, 14, t=t), text(px + 36, y + 47, sub, 12, "muted", t=t)]
        if i < len(steps) - 1:
            b.append(arrow(px + pw / 2, y + 62, y + 84, t))
        y += 84
    # Right panel: with what-changed (from examples/codex-run-2).
    rx, qx, qw = 470, 480, 430
    b += [rect(rx, 50, 450, 400, "panel", t), text(qx, 78, "With what-changed", 16, weight="600", fill="skill", t=t),
          rect(qx + 214, 62, 216, 22, "accent_bg", t, r=11),
          text(qx + 322, 77, "claim and report: real, codex-run-2", 11, anchor="middle", t=t)]
    y = 92
    b += [rect(qx, y, qw, 50, "bg", t), text(qx + 14, y + 21, "topics.yaml", 12, "muted", mono=True, t=t),
          text(qx + 14, y + 40, "agent-skills-adoption · 3 trusted sources · weekly", 13, t=t)]
    b.append(arrow(qx + qw / 2, y + 50, y + 66, t))
    y += 66
    b += [rect(qx, y, qw, 50, "bg", t), text(qx + 14, y + 21, "precheck.py, no model", 12, "muted", mono=True, t=t),
          text(qx + 14, y + 40, "Nothing changed? It writes “No change”: 0 tokens", 13, t=t)]
    b.append(arrow(qx + qw / 2, y + 50, y + 66, t))
    y += 66
    b += [rect(qx, y, qw, 104, "bg", t), text(qx + 14, y + 21, "ledger/agent-skills-adoption.md", 12, "muted", mono=True, t=t),
          text(qx + 14, y + 41, "C-005 · Codex scans .agents/skills up to the repo root", 13, weight="600", t=t),
          rect(qx + 14, y + 49, qw - 28, 22, "code_bg", t, r=4),
          text(qx + 22, y + 65, "“For repositories, Codex scans `.agents/skills`…”", 12, mono=True, t=t),
          text(qx + 14, y + 92, "T1 · read · confidence: medium · first seen 2026-10-14", 12, "muted", t=t)]
    b.append(arrow(qx + qw / 2, y + 104, y + 120, t))
    y += 120
    b += [rect(qx, y, qw, 50, "bg", t), text(qx + 14, y + 21, "digests/2026-10-14.md", 12, "muted", mono=True, t=t),
          text(qx + 14, y + 40, "New: C-001 … C-008 · Could not check: 2 sources", 13, t=t)]
    title = "What changes with the what-changed skill"
    desc = ("Side-by-side comparison of the same task. Left, labelled as an illustration and not a real run: "
            "without the skill you paste your old notes into the chat each time, the agent searches and answers "
            "with links, you work out what is new yourself, and nothing is kept for next time. Right, from the "
            "real example run codex-run-2 (the claim and the report): a topic with three trusted sources checked weekly; precheck.py writes "
            "'No change' without a model when nothing changed; each claim, such as C-005 about where Codex looks "
            "for skills, is kept in a ledger with a verbatim quote, the source tier T1, the label read, a "
            "confidence level and the date first seen; the daily digest lists only what is new (C-001 to C-008) "
            "and what could not be checked (2 sources).")
    return svg(w, h, title, desc, b, t)


# From docs/benchmark.md (27 items: 18 changed, 9 unchanged).
QUALITY = [  # label, skill (passed, total), plain agent (passed, total)
    ("Changes caught", (18, 18), (17, 18)),
    ("Current value right", (16, 18), (15, 18)),
    ("Unchanged items left alone", (9, 9), (8, 9)),
    ("Quotes found on the cited page", (47, 47), (24, 26)),
    ("Preferred by both judges", (13, 16), (3, 16)),
]
COST = [  # label, skill, plain agent, unit
    ("Input tokens per item", 507, 89, "k"),
    ("Minutes per topic", 4.6, 1.0, " min"),
]


def benchmark(t) -> str:
    w, h = 940, 430
    b = [text(w / 2, 30, "Skill vs. plain agent on 27 items (Claude Sonnet, same tools)", 18, weight="600", anchor="middle", t=t),
         rect(20, 50, 560, 360, "panel", t), rect(600, 50, 320, 360, "panel", t),
         text(34, 78, "Quality", 16, weight="600", t=t), text(118, 78, "higher is better", 12, "muted", t=t),
         text(614, 78, "Cost", 16, weight="600", t=t), text(660, 78, "lower is better", 12, "muted", t=t)]
    # Legend.
    b += [f'<rect x="300" y="66" width="12" height="12" rx="2" fill="{t["skill"]}"/>', text(318, 77, "what-changed", 12, t=t),
          f'<rect x="420" y="66" width="12" height="12" rx="2" fill="{t["plain"]}"/>', text(438, 77, "plain agent", 12, t=t)]
    bx, bw, y = 250, 270, 100
    for label, skill, plain in QUALITY:
        b.append(text(34, y + 15, label, 13, t=t))
        for k, ((p, n), color) in enumerate([(skill, "skill"), (plain, "plain")]):
            yy = y + k * 16
            frac = p / n
            b += [f'<rect x="{bx}" y="{yy}" width="{bw}" height="12" rx="2" fill="{t["border"]}" opacity="0.5"/>',
                  f'<rect x="{bx}" y="{yy}" width="{bw * frac:.1f}" height="12" rx="2" fill="{t[color]}"/>',
                  text(bx + bw + 8, yy + 11, f"{p}/{n}", 11, "muted", t=t)]
        y += 58
    b.append(text(34, 382, "Out of: 18 changed items (first two rows) · 9 unchanged items · checkable quotes", 11, "muted", t=t))
    b.append(text(34, 398, "· 16 items on which both judges preferred one side (11 ties)", 11, "muted", t=t))
    cx, cw, y = 614, 220, 104
    for label, skill, plain, unit in COST:
        top = max(skill, plain)
        b.append(text(cx, y, label, 13, t=t))
        for k, (v, color) in enumerate([(skill, "skill"), (plain, "plain")]):
            yy = y + 10 + k * 22
            b += [f'<rect x="{cx}" y="{yy}" width="{cw * v / top:.1f}" height="16" rx="2" fill="{t[color]}"/>',
                  text(cx + cw * v / top + 6, yy + 13, f"{v:g}{unit}", 12, "muted", t=t)]
        b.append(text(cx, y + 72, f"what-changed: {skill / plain:.1f}× the plain agent", 12, weight="600", t=t))
        y += 120
    b.append(text(614, 360, "Most input tokens are cache reads,", 11, "muted", t=t))
    b.append(text(614, 376, "billed at a fraction of normal input.", 11, "muted", t=t))
    title = "Benchmark: what-changed skill versus a plain agent"
    desc = ("Bar chart from docs/benchmark.md. Quality, higher is better, skill versus plain agent: changes caught 18 of "
            "18 versus 17 of 18; current value right 16 of 18 versus 15 of 18; unchanged items left alone 9 of 9 versus "
            "8 of 9; quotes found on the cited page 47 of 47 versus 24 of 26; preferred by both judges on 13 versus 3 of "
            "the 16 items that were not ties. Cost, lower is better: input tokens per item about 507 thousand versus 89 thousand, 5.7 "
            "times; minutes per topic 4.6 versus 1.0, 4.6 times.")
    return svg(w, h, title, desc, b, t)


def main() -> int:
    for name, draw in (("with-and-without", with_and_without), ("benchmark", benchmark)):
        for theme, t in THEMES.items():
            path = HERE / f"{name}-{theme}.svg"
            path.write_text(draw(t), encoding="utf-8")
            print(f"wrote {path.relative_to(HERE.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
