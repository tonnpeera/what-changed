---
topic: agent-skills-adoption
question: "Which agent products support the Agent Skills (SKILL.md) open standard, and where do they look for skills?"
last_run: 2026-10-14
next_claim_id: 7
---

## Source state
- https://agentskills.io/clients — fingerprint: "unavailable (fingerprint script DNS failure); web reader exposed only a JavaScript shell" — checked: 2026-10-14 — could not check: client list content not exposed
- https://github.com/agentskills/agentskills/commits/main.atom — fingerprint: "unavailable (fingerprint script DNS failure)" — checked: 2026-10-14 — could not check: web reader internal error
- https://agentskills.io/this-page-was-removed — fingerprint: "unavailable (fingerprint script DNS failure)" — checked: 2026-10-14 — could not check: web reader internal error
- https://agentskills.io/llms.txt — fingerprint: "Agent Skills docs index; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview — fingerprint: "Agent Skills; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://code.claude.com/docs/en/skills — fingerprint: "Extend Claude with skills; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://cursor.com/docs/skills — fingerprint: "Agent Skills; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills — fingerprint: "Adding agent skills for GitHub Copilot; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md — fingerprint: "using-agent-skills.md; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://developers.openai.com/api/docs/guides/tools-skills — fingerprint: "Skills; crawled 2026-10-14" — checked: 2026-10-14 — ok
- https://learn.chatgpt.com/docs/build-skills — fingerprint: "Build skills; crawled 2026-10-14" — checked: 2026-10-14 — ok

## Claims

### C-001 · Agent Skills is an open standard built around a SKILL.md manifest
- status: active
- confidence: high — official OpenAI documentation, read; counter-evidence search found no contrary official result
- sources:
  - [OpenAI Skills documentation](https://developers.openai.com/api/docs/guides/tools-skills) — T1 — read — quote: "Skills are compatible with the open Agent Skills standard."
  - [Claude Platform Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — T1 — read — quote: "Every Skill requires a `SKILL.md` file with YAML frontmatter:"
- counter-evidence: "Agent Skills standard not supported SKILL.md product limitation" (2026-10-14) → no contrary official result found; results instead included OpenAI's compatibility statement
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-002 · Claude Code supports custom Skills and discovers project skills from .claude/skills/
- status: active
- confidence: high — official Claude Code documentation, read; counter-evidence search found no contrary official result
- sources:
  - [Claude Code skills documentation](https://code.claude.com/docs/en/skills) — T1 — read — quote: "Claude Code loads project skills from `.claude/skills/` in the directory where you start it and in every parent directory up to the repository root."
  - [Claude Platform Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — T1 — read — quote: "Claude Code supports custom Skills."
- counter-evidence: "Claude Code SKILL.md support removed or limited" (2026-10-14) → no contrary official result found
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-003 · Cursor supports SKILL.md skills and scans .agents/skills/, .cursor/skills/, plus Claude and Codex skill directories
- status: active
- confidence: high — official Cursor documentation, read; counter-evidence search found no contrary official result
- sources:
  - [Cursor Agent Skills documentation](https://cursor.com/docs/skills) — T1 — read — quote: "For compatibility, Cursor also loads skills from Claude and Codex directories: `.claude/skills/`, `.codex/skills/`, `~/.claude/skills/`, and `~/.codex/skills/`."
  - [Cursor Agent Skills documentation](https://cursor.com/docs/skills) — T1 — read — quote: "Each skill should be a folder containing a `SKILL.md` file:"
- counter-evidence: "Cursor .agents skills not supported" (2026-10-14) → no contrary official result found; current Cursor documentation explicitly lists `.agents/skills/`
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-004 · GitHub Copilot supports agent skills in project .github/skills/, .claude/skills/, or .agents/skills/ and personal ~/.copilot/skills/ or ~/.agents/skills/
- status: active
- confidence: high — official GitHub documentation, read; counter-evidence search found no contrary official result
- sources:
  - [Adding agent skills for GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) — T1 — read — quote: "For project skills, specific to a single repository, create a `.github/skills`, `.claude/skills`, or `.agents/skills` directory in your repository."
  - [Adding agent skills for GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) — T1 — read — quote: "For personal skills, shared across projects, create a `~/.copilot/skills` or `~/.agents/skills` directory in your local home directory."
- counter-evidence: "GitHub Copilot SKILL.md unsupported" (2026-10-14) → no contrary official result found
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-005 · Gemini CLI supports Agent Skills and discovers them from built-in, extension, user, and workspace locations
- status: active
- confidence: high — official Gemini CLI documentation, read; counter-evidence search found no contrary official result
- sources:
  - [Gemini CLI Agent Skills documentation](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md) — T1 — read — quote: "Agent Skills provide Gemini CLI with specialized expertise on demand."
  - [Gemini CLI Agent Skills documentation](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md) — T1 — read — quote: "User Skills: Located in `~/.gemini/skills/` or the `~/.agents/skills/` alias."
- counter-evidence: "Gemini CLI Agent Skills removed" (2026-10-14) → no contrary official result found
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —

### C-006 · OpenAI's API and Codex support the Agent Skills format with progressive discovery of name/description before full SKILL.md instructions
- status: active
- confidence: high — official OpenAI documentation, read; counter-evidence search found no contrary official result
- sources:
  - [OpenAI Skills documentation](https://developers.openai.com/api/docs/guides/tools-skills) — T1 — read — quote: "Agents API sessions discover skills from directories in their sandbox."
  - [Build skills for ChatGPT and Codex](https://learn.chatgpt.com/docs/build-skills) — T1 — read — quote: "ChatGPT and Codex start with each skill’s name and description, then load the full `SKILL.md` instructions when they decide to use that skill."
- counter-evidence: "Codex SKILL.md support removed" (2026-10-14) → no contrary official result found
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —
