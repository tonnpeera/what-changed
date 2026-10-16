---
topic: agent-skills-adoption
question: "Which agent products support the Agent Skills (SKILL.md) open standard, and where do they look for skills?"
last_run: 2026-10-14
next_claim_id: 9
---

## Source state
- https://agentskills.io/clients → https://agentskills.io/clients.md — fingerprint: "516268fb253e" — checked: 2026-10-14 — ok
- https://github.com/agentskills/agentskills/commits/main.atom — fingerprint: "2026-08-09T20:36:04Z | docs: add OpenClaw to client showcase (#492)" — checked: 2026-10-14 — ok
- https://agentskills.io/this-page-was-removed — fingerprint: (none) — checked: 2026-10-14 — failed: HTTP 403

## Claims

### C-001 · Agent Skills is an open format requiring a directory with a SKILL.md manifest containing YAML frontmatter and Markdown body
- status: active
- confidence: high — official Agent Skills specification and OpenAI documentation, read
- sources:
  - [Agent Skills specification](https://agentskills.io/specification.md) — T1 — read — quote: "The SKILL.md file must contain YAML frontmatter followed by Markdown content."
  - [OpenAI Skills documentation](https://developers.openai.com/api/docs/guides/tools-skills.md) — T1 — read — quote: "Skills are compatible with the open Agent Skills standard."
- counter-evidence: "Agent Skills" standard discontinued OR dropped OR rolled back OR abandoned (2026-10-14) → none found; standard moved to GA in Claude API and expanded across multiple platforms
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-002 · The Agent Skills Client Showcase lists 46 agent products supporting the format
- status: active
- confidence: high — official Client Showcase catalog, read
- sources:
  - [Client Showcase](https://agentskills.io/clients.md) — T1 — read — quote: "Agent products that support the Agent Skills format."
- counter-evidence: "Agent Skills" format abandoned by clients OR client showcase deprecated (2026-10-14) → none found; showcase actively lists 46 agent tools
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-003 · Claude Code supports custom skills and discovers project skills from .claude/skills/ in the starting directory and parent directories
- status: active
- confidence: high — official Claude Code documentation, read
- sources:
  - [Claude Code skills documentation](https://code.claude.com/docs/en/skills.md) — T1 — read — quote: "Claude Code loads project skills from .claude/skills/ in the directory where you start it"
- counter-evidence: "Claude Code" "Agent Skills" removed OR deprecated OR unsupported (2026-10-14) → none found; custom commands were merged into skills
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-004 · Cursor supports Agent Skills and loads them from .agents/skills/, .cursor/skills/, and compatibility directories
- status: active
- confidence: high — official Cursor documentation, read
- sources:
  - [Cursor Agent Skills documentation](https://cursor.com/docs/context/skills) — T1 — read — quote: "For compatibility, Cursor also loads skills from Claude and Codex directories: .claude/skills/, .codex/skills/, ~/.claude/skills/, and ~/.codex/skills/."
- counter-evidence: Cursor OR "GitHub Copilot" "Agent Skills" removed OR discontinued OR unsupported (2026-10-14) → none found; Cursor natively supports .cursor/skills/ and .agents/skills/
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-005 · GitHub Copilot supports project skills in .github/skills, .claude/skills, or .agents/skills and personal skills in ~/.copilot/skills or ~/.agents/skills
- status: active
- confidence: high — official GitHub Copilot documentation, read
- sources:
  - [GitHub Copilot agent skills documentation](https://docs.github.com/api/article/body?pathname=/en/copilot/concepts/agents/about-agent-skills) — T1 — read — quote: "Project skills, stored in your repository (.github/skills, .claude/skills, or .agents/skills)"
- counter-evidence: "GitHub Copilot" "Agent Skills" dropped OR discontinued OR not supported (2026-10-14) → none found; Copilot supports cloud agent, CLI, and IDE agent modes
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-006 · Gemini CLI supports Agent Skills open standard across built-in, extension, user, and workspace discovery tiers
- status: active
- confidence: high — official Gemini CLI documentation, read
- sources:
  - [Gemini CLI skills documentation](https://geminicli.com/docs/cli/skills.md) — T1 — read — quote: "Agent Skills let you extend Gemini CLI with specialized expertise, procedural workflows, and task-specific resources."
- counter-evidence: "Gemini CLI" "Agent Skills" removed OR dropped OR deprecated (2026-10-14) → none found; Gemini CLI provides /skills and terminal gemini skills commands
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-007 · The Agent Skills specification requires two frontmatter fields: name (max 64 characters) and description (max 1024 characters)
- status: active
- confidence: high — official Agent Skills specification, read
- sources:
  - [Agent Skills specification](https://agentskills.io/specification.md) — T1 — read — quote: "Max 64 characters. Lowercase letters, numbers, and hyphens only. Must not start or end with a hyphen."
- counter-evidence: "Agent Skills" specification changes 2026 (2026-10-14) → none found; specification maintains required name and description fields
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-008 · The newest commit in the agentskills/agentskills repository Atom feed is from August 2026 adding OpenClaw to the client showcase
- status: active
- confidence: high — official GitHub Atom feed, read
- sources:
  - [agentskills commits feed](https://github.com/agentskills/agentskills/commits/main.atom) — T1 — read — quote: "docs: add OpenClaw to client showcase (#492)"
- counter-evidence: agentskills repository commits rollback (2026-10-14) → none found; commit #492 remains the newest entry on the main branch
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2026-11-14
- superseded_by: —
