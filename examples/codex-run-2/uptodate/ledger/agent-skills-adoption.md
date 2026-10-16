---
topic: agent-skills-adoption
question: "Which agent products support the Agent Skills (SKILL.md) open standard, and where do they look for skills?"
last_run: 2026-10-14
next_claim_id: 9
---

## Source state
- https://agentskills.io/clients -> https://raw.githubusercontent.com/agentskills/agentskills/main/docs/snippets/clients.jsx — fingerprint: "clients array: 46 entries; last entry OpenClaw" — checked: 2026-10-14 — ok
- https://github.com/agentskills/agentskills/commits/main.atom — fingerprint: unavailable — checked: 2026-10-14 — failed: web tool rejected application/atom+xml; shell fingerprint helper could not resolve the host
- https://agentskills.io/this-page-was-removed — fingerprint: unavailable — checked: 2026-10-14 — failed: URL inaccessible to web tool; shell fingerprint helper could not resolve the host

## Claims

### C-001 · The official showcase currently lists 46 products as supporting Agent Skills
- status: active
- confidence: medium — official showcase data, read; counter-evidence not searched (budget)
- sources:
  - [Client Showcase data](https://raw.githubusercontent.com/agentskills/agentskills/main/docs/snippets/clients.jsx) — T1 — read — quote: "Shared client data for the Agent Skills documentation."
  - [Client Showcase page](https://agentskills.io/clients) — T1 — read — quote: "Client Showcase"
- counter-evidence: "Agent Skills client showcase list outdated or unsupported clients" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —
- note: The current data includes Junie, Gemini CLI, OpenCode, OpenHands, Cursor, Amp, Goose, GitHub Copilot, VS Code, Claude Code, ChatGPT & Codex, and many others through OpenClaw.

### C-002 · The portable core is a skill directory containing SKILL.md with required name and description fields
- status: active
- confidence: medium — official specification, read; counter-evidence not searched (budget)
- sources:
  - [Agent Skills specification](https://raw.githubusercontent.com/agentskills/agentskills/main/docs/specification.mdx) — T1 — read — quote: "A skill is a directory containing, at minimum, a `SKILL.md` file:"
  - [Agent Skills specification](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx) — T1 — read — quote: "The `SKILL.md` file must contain YAML frontmatter followed by Markdown content."
- counter-evidence: "Agent Skills specification name description not required" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-003 · Discovery is client-specific: local agents can scan filesystem directories, while cloud or sandboxed agents need an API, registry, or bundled assets
- status: active
- confidence: medium — official implementation guide, read; counter-evidence not searched (budget)
- sources:
  - [Adding skills support](https://raw.githubusercontent.com/agentskills/agentskills/main/docs/client-implementation/adding-skills-support.mdx) — T1 — read — quote: "A locally-running agent can scan the user's filesystem for skill directories."
- counter-evidence: "Agent Skills discovery mechanism is standardized across clients" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-004 · Claude Code discovers project skills under .claude/skills/<skill-name>/SKILL.md
- status: active
- confidence: medium — official Claude Code documentation, read; counter-evidence not searched (budget)
- sources:
  - [Claude Code skills](https://code.claude.com/docs/en/skills) — T1 — read — quote: "Project | `.claude/skills/<skill-name>/SKILL.md` | Sessions in this repository."
- counter-evidence: "Claude Code no longer loads project .claude/skills" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-005 · Codex scans .agents/skills in the current directory and parent directories up to the repository root
- status: active
- confidence: medium — official Codex documentation, read; counter-evidence not searched (budget)
- sources:
  - [Codex skills](https://developers.openai.com/codex/skills/) — T1 — read — quote: "For repositories, Codex scans `.agents/skills` in every directory from your current working directory up to the repository root."
- counter-evidence: "Codex .agents/skills discovery removed or changed" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-006 · VS Code supports project skills in .github/skills, .claude/skills, and .agents/skills, plus corresponding user-level roots
- status: active
- confidence: medium — official VS Code documentation, read; counter-evidence not searched (budget)
- sources:
  - [Agent Skills in VS Code](https://code.visualstudio.com/docs/copilot/customization/agent-skills) — T1 — read — quote: "Project skills, stored in your repository | `.github/skills/`, `.claude/skills/`, `.agents/skills/`"
- counter-evidence: "VS Code Agent Skills paths changed" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-007 · Cursor loads project skills from .agents/skills and .cursor/skills and also supports Claude and Codex skill roots
- status: active
- confidence: medium — official Cursor documentation, read; counter-evidence not searched (budget)
- sources:
  - [Cursor skills](https://cursor.com/docs/skills) — T1 — read — quote: "For compatibility, Cursor also loads skills from Claude and Codex directories: `.claude/skills/`, `.codex/skills/`, `~/.claude/skills/`, and `~/.codex/skills/`."
- counter-evidence: "Cursor no longer loads .agents/skills or .cursor/skills" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-008 · Cursor recursively discovers SKILL.md files in nested project skill directories
- status: active
- confidence: medium — official Cursor documentation, read; counter-evidence not searched (budget)
- sources:
  - [Cursor skills](https://cursor.com/docs/skills) — T1 — read — quote: "Cursor walks the skills root recursively and picks up any `SKILL.md` it finds:"
- counter-evidence: "Cursor nested Agent Skills discovery does not work" (2026-10-14) -> not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —
