"""Offline tests for the skill's scripts. Run: python3 -m unittest discover -s tests"""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# run-daily.sh needs bash; symlinks and FIFOs work differently on Windows (run-daily.ps1 is not covered here).
POSIX_ONLY = unittest.skipIf(os.name == "nt", "needs bash, POSIX symlinks or FIFOs")


def _can_symlink() -> bool:
    """Windows allows symlinks only with Developer Mode or admin rights."""
    with tempfile.TemporaryDirectory() as d:
        try:
            (Path(d) / "link").symlink_to(Path(d) / "target")
            return True
        except (OSError, NotImplementedError):
            return False


NEEDS_SYMLINKS = unittest.skipUnless(_can_symlink(), "this account may not create symlinks")
SCRIPTS = ROOT / "skills" / "what-changed" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "evals"))

import catch_up  # noqa: E402
import cli_version  # noqa: E402
import ledger  # noqa: E402
import check_ledger  # noqa: E402
import fingerprint  # noqa: E402
import host_tokens  # noqa: E402
import hosts  # noqa: E402
import log_run  # noqa: E402
import precheck  # noqa: E402
import net  # noqa: E402
import verify_quotes  # noqa: E402
from ledger import parse_ledger  # noqa: E402

LEDGER = """---
topic: demo
last_run: 2026-10-14
next_claim_id: 4
---

## Claims

### C-001 · Old price is $2
- status: superseded
- confidence: medium — official page, read
- sources:
  - [pricing](https://example.com/p) — T1 — read — quote: "costs $2 per month"
- counter-evidence: "price rise" 2026-10-01 → none found
- asserted_by: agent
- first_seen: 2026-09-01 · last_confirmed: 2026-10-01 · review_by: 2026-11-01
- superseded_by: C-002

### C-002 · New price is $3 from 2026-10-10
- status: active
- confidence: high — official page, read
- sources:
  - [pricing](https://example.com/p) — T1 — read — quote: "now costs $3 per month"
- counter-evidence: "price rollback" 2026-10-14 → none found
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2026-11-14
- superseded_by: —

### C-003 · A forum says a free tier is coming
- status: active
- confidence: {level} — forum post only
- sources:
  - [forum](https://example.org/t/1) — T4 — search-snippet
- counter-evidence: not searched (budget)
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2026-11-14
- superseded_by: —
"""


def write_store(tmp: Path, level: str = "very-low") -> Path:
    (tmp / "ledger").mkdir(parents=True)
    (tmp / "ledger" / "demo.md").write_text(LEDGER.replace("{level}", level), encoding="utf-8")
    return tmp


class LedgerTests(unittest.TestCase):
    def test_parse_claims_sources_and_hyphenated_fields(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = parse_ledger(write_store(Path(d)) / "ledger" / "demo.md")
        self.assertEqual([c.id for c in ledger.claims], ["C-001", "C-002", "C-003"])
        self.assertEqual(ledger.claims[1].sources[0].quote, "now costs $3 per month")
        self.assertIn("counter-evidence", ledger.claims[2].fields)
        self.assertEqual(ledger.claims[0].dates["review_by"], "2026-11-01")

    def test_valid_ledger_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _, failures = check_ledger.check([write_store(Path(d)) / "ledger" / "demo.md"])
        self.assertEqual(failures, [])

    def test_t4_only_claim_cannot_be_rated_above_very_low(self):
        with tempfile.TemporaryDirectory() as d:
            _, failures = check_ledger.check([write_store(Path(d), "medium") / "ledger" / "demo.md"])
        self.assertTrue(any("C-003" in f and "ceiling" in f for f in failures))

    def test_high_without_counter_evidence_is_capped(self):
        text = LEDGER.replace("{level}", "very-low").replace(
            '- counter-evidence: "price rollback" 2026-10-14 → none found', "- counter-evidence: not searched (budget)")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "demo.md"
            p.write_text(text, encoding="utf-8")
            _, failures = check_ledger.check([p])
        self.assertTrue(any("C-002" in f and "ceiling medium" in f for f in failures))

    def test_long_thai_quote_is_caught(self):
        """A Thai quote has no spaces, so it is limited by characters, not words."""
        long_thai = "ก" * 200
        text = LEDGER.replace("{level}", "very-low").replace("now costs $3 per month", long_thai)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "demo.md"
            p.write_text(text, encoding="utf-8")
            _, failures = check_ledger.check([p])
        self.assertTrue(any("quote" in f and "characters" in f for f in failures), failures)

    def test_source_state_lines_must_be_readable(self):
        """Source state lines that precheck cannot parse are reported."""
        text = LEDGER.replace("{level}", "very-low").replace(
            "## Claims", "## Source state\n- https://example.com/p (main page) fingerprint 2.1\n\n## Claims")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "demo.md"
            p.write_text(text, encoding="utf-8")
            _, failures = check_ledger.check([p])
        self.assertTrue(any("Source state" in f for f in failures), failures)

    def test_superseded_must_point_to_existing_claim(self):
        text = LEDGER.replace("{level}", "very-low").replace("- superseded_by: C-002", "- superseded_by: C-099")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "demo.md"
            p.write_text(text, encoding="utf-8")
            _, failures = check_ledger.check([p])
        self.assertTrue(any("superseded" in f for f in failures))


    def test_a_claim_that_replaces_another_states_when_it_took_effect(self):
        """A changed value needs its effective date, or an explicit "effective date not stated"."""
        for title, ok in [("New price is $3 from 2026-10-10", True), ("New price is $3 (effective date not stated)", True),
                          ("New price is $3", False)]:
            with self.subTest(title=title), tempfile.TemporaryDirectory() as d:
                p = Path(d) / "demo.md"
                p.write_text(LEDGER.format(level="very-low").replace("New price is $3 from 2026-10-10", title), encoding="utf-8")
                results, failures = check_ledger.check([p])
                rule = "a claim that replaces another states when it took effect"
                self.assertEqual(results[rule], [1 if ok else 0, 1], failures)


class QuoteTests(unittest.TestCase):
    def test_markdown_keeps_angle_brackets(self):
        page = verify_quotes.page_text("Put it in `.agents/skills/<skill-name>/SKILL.md`.")
        self.assertIn(verify_quotes.normalise(".agents/skills/<skill-name>/SKILL.md"), page)

    def test_inline_tags_do_not_split_thai_words(self):
        """<a>/<span> inside a Thai sentence must not add spaces."""
        page = verify_quotes.page_text('<html><body><p><a href="/ai">AI</a>มี<span>สัดส่วน</span>มาก</p></body></html>')
        self.assertIn(verify_quotes.quote_key("AIมีสัดส่วนมาก"), page)
        page2 = verify_quotes.page_text("<html><body><p>The <b>price</b> is <em>now</em> $3.</p></body></html>")
        self.assertIn(verify_quotes.quote_key("The price is now $3."), page2)

    def test_html_tags_are_stripped_and_quotes_normalised(self):
        page = verify_quotes.page_text("<html><body><p>It’s <b>now</b> $3</p><script>x()</script></body></html>")
        self.assertIn(verify_quotes.normalise("It's now $3"), page)
        self.assertNotIn("x()", page)


class FingerprintTests(unittest.TestCase):
    def test_changelog_feed_and_page(self):
        cases = {
            "https://x/CHANGELOG.md": ("# Changelog\n\n## 2.1.296\n- a\n## 2.1.295\n", "changelog", "2.1.296"),
            "https://x/feed.xml": ("<?xml?><rss><channel><item><title>Hello</title><pubDate>Tue</pubDate></item></channel></rss>",
                                   "feed", "Tue | Hello"),
        }
        for url, (body, kind, fp) in cases.items():
            with mock.patch.object(fingerprint, "fetch", return_value=net.Fetched(body, "ok", url)):
                r = fingerprint.fingerprint(url, 5)
            self.assertEqual((r["kind"], r["fingerprint"]), (kind, fp))

    def test_redirect_is_reported(self):
        """A watchlist URL that redirects elsewhere is reported."""
        r = net.Fetched("<html><title>Jobs in Thailand</title></html>", "ok", "https://other.example/home")
        with mock.patch.object(fingerprint, "fetch", return_value=r):
            out = fingerprint.fingerprint("https://example.com/specific-page", 5)
        self.assertEqual(out["final_url"], "https://other.example/home")
        self.assertIn("redirected", out["detail"])

    def test_empty_release_feed_and_failure(self):
        with mock.patch.object(fingerprint, "fetch", return_value=net.Fetched("<feed></feed>", "ok", "https://github.com/o/r/releases.atom")):
            r = fingerprint.fingerprint("https://github.com/o/r/releases", 5)
        self.assertEqual(r["fingerprint"], "(no items)")
        with mock.patch.object(fingerprint, "fetch", return_value=net.Fetched(None, "HTTP 404", "https://x/gone")):
            r = fingerprint.fingerprint("https://x/gone", 5)
        self.assertFalse(r["ok"])
        self.assertEqual(r["detail"], "HTTP 404")


class CatchUpTests(unittest.TestCase):
    def run_catch_up(self, store: Path, fmt: str = "plain") -> str:
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["catch_up.py", "--store", str(store), "--format", fmt]), redirect_stdout(buf):
            catch_up.main()
        return buf.getvalue()

    def test_reminds_once_per_day_then_silent_after_run(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "runs.log").write_text("2026-10-09T18:00:00+00:00\tmode=manual-seed\n", encoding="utf-8")
            first = self.run_catch_up(store, "gemini")
            self.assertIn("additionalContext", json.loads(first)["hookSpecificOutput"])
            self.assertEqual(self.run_catch_up(store), "")  # already reminded today
            (store / ".catchup-notified").unlink()
            today = date.today().isoformat()
            with open(store / "runs.log", "a", encoding="utf-8") as f:
                f.write(f"{today}T06:00:00+00:00\tscope=topics\tmode=demo:light\tdue=1/2\n")
            self.assertNotEqual(self.run_catch_up(store), "")  # one named topic is not today's run
            (store / ".catchup-notified").unlink()
            with open(store / "runs.log", "a", encoding="utf-8") as f:
                f.write(f"{today}T07:00:00+00:00\tscope=all\tmode=demo:light\tdue=2/2\n")
            self.assertEqual(self.run_catch_up(store), "")  # ran today

    def test_legacy_lines_without_scope(self):
        self.assertTrue(catch_up.is_daily_run("2026-10-14T00:52\tmode=light\tdue=2/2"))
        self.assertFalse(catch_up.is_daily_run("2026-10-14T00:54\tmode=light\tdue=1/2"))
        self.assertFalse(catch_up.is_daily_run("2026-10-09T18:00\tmode=manual-seed\tdue=1/1"))

    def test_formats(self):
        self.assertEqual(json.loads(catch_up.render("x", "cursor")), {"additional_context": "x"})
        self.assertEqual(json.loads(catch_up.render("x", "copilot")), {"additionalContext": "x"})
        self.assertEqual(catch_up.render("x", "codex"), "x")

    def test_autorun_changes_the_request(self):
        with mock.patch.dict(os.environ, {"WHAT_CHANGED_AUTORUN": "1"}):
            self.assertIn("Before anything else", catch_up.message(Path("s"), None, True))
        self.assertIn("Do not run it without their yes", catch_up.message(Path("s"), None, False))


TOPICS = """topics:
  - id: demo
    question: "What changed?"   # comment
    sources:
      - https://example.com/CHANGELOG.md
    cadence: daily
    budget: { pages: 5, searches: 4 }
    recheck_low: true
    languages: [en]
"""

DEMO_LEDGER = """---
topic: demo
last_run: 2026-10-14
next_claim_id: 2
---

## Source state
- https://example.com/CHANGELOG.md — fingerprint: "2.1.296" — checked: 2026-10-14 — ok

## Claims

### C-001 · Version 2.1.296 is the newest
- status: active
- confidence: high — changelog, read
- sources:
  - [changelog](https://example.com/CHANGELOG.md) — T1 — read — quote: "2.1.296"
- counter-evidence: "rollback" 2026-10-14 → none found
- asserted_by: agent
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —
"""


class PrecheckTests(unittest.TestCase):
    def make_store(self, d: str) -> Path:
        store = Path(d)
        (store / "ledger").mkdir()
        (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")
        (store / "ledger" / "demo.md").write_text(DEMO_LEDGER, encoding="utf-8")
        (store / "runs.log").write_text("2026-10-14T07:00:00+00:00\tscope=all\tdue=1/1\n", encoding="utf-8")
        return store

    def fp(self, value):
        return mock.patch.object(precheck, "fingerprint", return_value={
            "url": "u", "ok": True, "kind": "changelog", "fingerprint": value, "detail": "", "partial": False})

    def test_reads_simple_topics_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            topics = precheck.read_topics(self.make_store(d) / "topics.yaml")
        self.assertEqual(topics[0]["id"], "demo")
        self.assertEqual(topics[0]["sources"], ["https://example.com/CHANGELOG.md"])
        self.assertEqual(topics[0]["recheck_low"], "true")

    def test_rejects_path_traversal_in_topic_id(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            (store / "topics.yaml").write_text(TOPICS.replace("id: demo", "id: ../../evil"), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), 2)
        with self.assertRaises(precheck.TopicsFormatError):
            precheck.ledger_path_for(Path("/tmp/s"), "../x")

    def test_compares_meaningful_part(self):
        self.assertEqual(precheck.comparable("v2.1.295", None), precheck.comparable("2026-10-09T19:28Z | v2.1.295", "release-feed"))
        self.assertEqual(precheck.comparable("Title | H1 | abc123", None), "abc123")

    def test_quiet_day_writes_digest_and_log_without_agent(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            with self.fp("2.1.296"), redirect_stdout(io.StringIO()):
                code = precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
            self.assertEqual(code, 0)
            log = (store / "runs.log").read_text(encoding="utf-8").splitlines()[-1]
            self.assertTrue(log.startswith("2026-10-15") and "scope=all" in log and "tokens=0" in log)
            self.assertIn("No change", (store / "digests" / "2026-10-15.md").read_text(encoding="utf-8"))
            self.assertIn("last_run: 2026-10-15", (store / "ledger" / "demo.md").read_text(encoding="utf-8"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), 0)
            self.assertEqual(len((store / "runs.log").read_text(encoding="utf-8").splitlines()), 2)  # no second run

    def test_changed_source_needs_agent_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            buf = io.StringIO()
            with self.fp("2.1.297"), redirect_stdout(buf):
                code = precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
            self.assertEqual(code, precheck.NEEDS_AGENT)
            self.assertIn("source changed", buf.getvalue())
            self.assertFalse((store / "digests").exists())

    def test_local_block_is_named_not_treated_as_dead_site(self):
        """Sources refused by the sandbox proxy get a clear hint."""
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            blocked = {"url": "u", "ok": False, "kind": None, "fingerprint": None, "partial": False,
                       "detail": "blocked-local (blocked by a local proxy or sandbox, not the site: allow this host: example.com)"}
            buf = io.StringIO()
            with mock.patch.object(precheck, "fingerprint", return_value=blocked), redirect_stdout(buf):
                precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
            self.assertIn("blocked by a local proxy or sandbox", buf.getvalue())
            self.assertIn("hosts.py", buf.getvalue())
            self.assertEqual(hosts.hosts(store), (["example.com"], []))

    def test_recheck_low_follows_cadence(self):
        """With recheck_low: true, a low claim in a weekly topic is re-checked when the
        topic is due (a week later), not the next day."""
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            (store / "topics.yaml").write_text(TOPICS.replace("cadence: daily", "cadence: weekly"), encoding="utf-8")
            p = store / "ledger" / "demo.md"
            p.write_text(p.read_text(encoding="utf-8").replace("confidence: high", "confidence: low"), encoding="utf-8")
            with self.fp("2.1.296"), redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), 0)
            with self.fp("2.1.296"), redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-21"]),
                                 precheck.NEEDS_AGENT)

    def test_hosts_ignore_free_text_and_odd_names(self):
        """Only structured URL fields count; quotes cannot add hosts; odd names are dropped."""
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            p = store / "ledger" / "demo.md"
            p.write_text(p.read_text(encoding="utf-8").replace(
                'quote: "2.1.296"', 'quote: "see https://evil.example/x"') + "\n- note: https://notes.example/y\n", encoding="utf-8")
            self.assertEqual(hosts.hosts(store), (["example.com"], []))
        self.assertIsNone(hosts._host("https://*.example.com/"))
        self.assertIsNone(hosts._host("file:///etc/hosts"))

    def test_low_claim_with_recheck_needs_agent(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.make_store(d)
            p = store / "ledger" / "demo.md"
            p.write_text(p.read_text(encoding="utf-8").replace("confidence: high", "confidence: low"), encoding="utf-8")
            with self.fp("2.1.296"), redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]),
                                 precheck.NEEDS_AGENT)



class HostTokensTests(unittest.TestCase):
    def test_parses_each_host_format(self):
        self.assertEqual(host_tokens.tokens("codex", "...\ntokens used\n1,234\nmore\ntokens used\n125,572\n"), 125572)
        self.assertEqual(host_tokens.tokens("antigravity", '{"usage": {"total_tokens": 11072}}'), 11072)
        self.assertEqual(host_tokens.tokens("claude", 'x {"usage": {"input_tokens": 10, "output_tokens": 5}}'), 15)
        self.assertIsNone(host_tokens.tokens("codex", "no numbers here"))

    def test_fills_unknown_once(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "runs.log").write_text("2026-10-14T01:00\tscope=topics\ttokens=unknown\n", encoding="utf-8")
            (store / "out.txt").write_text("tokens used\n42\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                host_tokens.main(["x", "codex", str(store / "out.txt"), str(store)])
            self.assertIn("tokens=42", (store / "runs.log").read_text(encoding="utf-8"))




class _FakeResp:
    def __init__(self, body: bytes, length: int | None, url="https://example.com/p"):
        self.body, self._url = body, url
        self.headers = __import__("email.message", fromlist=["Message"]).Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def geturl(self):
        return self._url

    def read(self, amt=None):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class NetTests(unittest.TestCase):
    def test_short_body_without_error_is_partial_not_ok(self):
        """A proxy cut the body short and urllib raised nothing."""
        with mock.patch.object(net, "_open", return_value=_FakeResp(b"x" * 60, 100)):
            text, status = net.get("https://example.com/p", retries=1)
        self.assertEqual(status, "partial")

    def test_full_body_is_ok(self):
        with mock.patch.object(net, "_open", return_value=_FakeResp(b"x" * 100, 100)):
            self.assertEqual(net.get("https://example.com/p")[1], "ok")

    def test_proxy_refusal_is_reported_as_local_block(self):
        """The sandbox proxy refuses hosts that are not allowed."""
        err = __import__("urllib.error", fromlist=["URLError"]).URLError("Tunnel connection failed: 403 Forbidden")
        with mock.patch.object(net, "_open", side_effect=err):
            text, status = net.get("https://example.com/p")
        self.assertIsNone(text)
        self.assertTrue(status.startswith("blocked-local"), status)

    def test_non_ascii_url_is_percent_encoded(self):
        """A URL with a Thai path is percent-encoded, not a crash."""
        seen = {}
        def fake(req, *a, **kw):
            seen["url"] = req.full_url
            return _FakeResp(b"ok", 2)
        with mock.patch.object(net, "_open", side_effect=fake):
            net.get("https://th.wikipedia.org/wiki/กรุงเทพมหานคร")
        seen["url"].encode("ascii")  # raises if anything is left unencoded



class ReportingTests(unittest.TestCase):
    """PDFs, repeated URLs, host lists, not-due topics and dated release notes."""

    def ledger_with_quotes(self, d, url, quotes):
        store = Path(d)
        (store / "ledger").mkdir()
        blocks = []
        for i, q in enumerate(quotes, 1):
            blocks.append(f"""### C-00{i} · claim {i}
- status: active
- confidence: medium — x
- sources:
  - [doc]({url}) — T1 — read — quote: "{q}"
- counter-evidence: "x" 2026-10-14 → none found
- first_seen: 2026-10-14 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
""")
        (store / "ledger" / "t.md").write_text("---\ntopic: t\n---\n\n## Claims\n\n" + "\n".join(blocks), encoding="utf-8")
        return store

    def run_vq(self, store):
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["verify_quotes.py", str(store)]), redirect_stdout(buf):
            verify_quotes.main(["verify_quotes.py", str(store)])
        return buf.getvalue()

    def test_pdf_is_unsupported_not_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.ledger_with_quotes(d, "https://x.example/a.pdf", ["tax rate 15%"])
            pdf = net.Fetched("%PDF-1.7 binary stuff", "ok", "https://x.example/a.pdf", 20, 20, "application/pdf")
            with mock.patch.object(verify_quotes, "fetch", return_value=pdf):
                out = self.run_vq(store)
        self.assertNotIn("NOT FOUND", out)
        self.assertIn("pdf", out.lower())

    def test_same_url_gets_one_status(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.ledger_with_quotes(d, "https://x.example/p", ["first quote", "second quote"])
            short = net.Fetched("<html><body>nothing here</body></html>", "ok", "https://x.example/p", 40, None, "text/html")
            longer = net.Fetched("<html><body>first quote and more text here</body></html>", "partial", "https://x.example/p", 60, 100, "text/html")
            with mock.patch.object(verify_quotes, "fetch", side_effect=[short, longer, longer]):
                out = self.run_vq(store)
        # first quote found in the longer copy; second quote is in neither: the URL is partial, so it is
        # "truncated", not "NOT FOUND" for one claim and "truncated" for another.
        self.assertNotIn("NOT FOUND", out)
        self.assertIn("TRUNCATED", out)

    def test_hosts_comma_prints_only_the_comma_line(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.ledger_with_quotes(d, "https://other.example/p", ["q"])
            (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            from contextlib import redirect_stderr
            with redirect_stdout(out), redirect_stderr(err):
                hosts.main(["hosts.py", "--store", str(store), "--comma"])
        self.assertEqual(out.getvalue().strip(), "example.com")
        self.assertEqual(err.getvalue(), "")

    def test_precheck_lists_not_due_topics_when_agent_needed(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "ledger").mkdir()
            two = TOPICS + TOPICS.replace("id: demo", "id: other").replace("cadence: daily", "cadence: monthly").split("topics:\n", 1)[1]
            (store / "topics.yaml").write_text(two, encoding="utf-8")
            (store / "ledger" / "other.md").write_text(DEMO_LEDGER.replace("topic: demo", "topic: other"), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
        self.assertEqual(code, precheck.NEEDS_AGENT)  # demo has no ledger yet
        self.assertIn("not due: [other] (next: 2026-11-13)", buf.getvalue())

    def test_dated_release_notes_are_a_changelog(self):
        body = "# Release notes\n\n### October 14, 2026\n- a\n\n### October 7, 2026\n- b\n"
        with mock.patch.object(fingerprint, "fetch", return_value=net.Fetched(body, "ok", "https://x/notes.md")):
            r = fingerprint.fingerprint("https://x/notes.md", 5)
        self.assertEqual((r["kind"], r["fingerprint"]), ("changelog", "October 14, 2026"))


class SecurityTests(unittest.TestCase):
    """Unattended runs: fetch limits, where the skill may be installed, isolated Python."""

    def test_local_and_private_addresses_are_refused(self):
        for url in ["http://localhost/x", "http://a.localhost/", "http://127.0.0.1:8080/",
                    "http://10.0.0.5/", "http://192.168.1.1/", "http://169.254.169.254/latest/",
                    "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://2130706433/", "http://0x7f.1/",
                    "http://127%2e0.0.1:8/", "http://%6cocalhost/", "http://０.０.０.０:631/",
                    "http://127。0。0。1/", "http://①②⑦.0.0.1/", "http://[64:ff9b::7f00:1]/",
                    "http://[2002:7f00:1::]/", "http://[fe80::1%25en0]/", "http://LOCALHOST./",
                    "http://127.0.0.1%23@evil.example/", "http://127.0.0.1%40evil.example/",
                    "http://127.0.0.1%2fx@evil.example/", "http://user@127.0.0.1/", "http://[::1]%40evil.example/",
                    "ftp://example.com/x", "file:///etc/passwd"]:
            with self.subTest(url=url):
                self.assertIsNotNone(net.refused(url))
                text, status = net.get(url)
                self.assertIsNone(text)
                self.assertTrue(status.startswith("refused"), status)

    def test_name_resolving_to_private_address_is_refused_without_proxy(self):
        infos = [(2, 1, 6, "", ("192.168.0.9", 0))]
        with mock.patch("urllib.request.getproxies", return_value={}), \
             mock.patch("socket.getaddrinfo", return_value=infos):
            self.assertIn("private", net.refused("https://evil.example/") or "")
        with mock.patch("urllib.request.getproxies", return_value={}), \
             mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 0))]):
            self.assertIsNone(net.refused("https://example.com/"))
            self.assertIsNone(net.refused("https://93.184.215.14/"))
            self.assertIsNone(net.refused("https://[2606:2800:21f:cb07:6820:80da:af6b:8b2c]/"))

    LOCAL_ANSWERS = ["192.168.0.9", "10.1.2.3", "172.16.0.1", "127.0.0.1", "169.254.169.254",
                     "::1", "fe80::1%en0", "fd00::7", "::ffff:10.0.0.1"]

    def resolving_to(self, address: str, proxies: dict):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [mock.patch("urllib.request.getproxies", return_value=proxies),
                mock.patch("urllib.request.proxy_bypass", return_value=False),
                mock.patch("socket.getaddrinfo", return_value=[(family, 1, 6, "", (address, 0))])]

    def test_names_resolving_to_local_addresses_are_refused_with_and_without_proxy(self):
        """A proxy must not open the way to the LAN: the name is resolved and checked anyway."""
        for proxies in ({}, {"https": "http://127.0.0.1:9", "http": "http://127.0.0.1:9"}):
            for address in self.LOCAL_ANSWERS:
                with self.subTest(proxy=bool(proxies), address=address):
                    patches = self.resolving_to(address, proxies)
                    with patches[0], patches[1], patches[2]:
                        self.assertIn("private", net.refused("https://intranet.example/") or "")
                        self.assertIn("private", net.refused("http://intranet.example/") or "")

    def test_behind_a_proxy_unresolvable_names_are_left_to_the_proxy(self):
        """Inside a sandbox local DNS often fails; the proxy resolves the name then."""
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://127.0.0.1:9"}), \
             mock.patch("urllib.request.proxy_bypass", return_value=False), \
             mock.patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "not known")):
            self.assertIsNone(net.refused("https://example.com/"))
            self.assertIsNotNone(net.refused("https://127.0.0.1/"))
            self.assertIsNotNone(net.refused("https://169.254.169.254/"))
            self.assertIsNotNone(net.refused("https://localhost/"))

    def test_behind_a_proxy_public_and_fake_ip_answers_pass(self):
        """Public answers pass; so do the stand-in answers (198.18.0.0/15) of fake-ip proxy apps."""
        proxies = {"https": "http://127.0.0.1:9"}
        for address in ["93.184.215.14", "2606:2800:21f:cb07:6820:80da:af6b:8b2c", "198.18.0.5", "198.19.255.1"]:
            with self.subTest(address=address):
                patches = self.resolving_to(address, proxies)
                with patches[0], patches[1], patches[2]:
                    self.assertIsNone(net.refused("https://example.com/"))
        patches = self.resolving_to("198.18.0.5", {})
        with patches[0], patches[1], patches[2]:
            self.assertIsNotNone(net.refused("https://example.com/"))  # without a proxy we connect there

    def test_every_redirect_hop_is_checked(self):
        import urllib.request as ur
        from http.client import HTTPMessage
        h = net._CheckedRedirect()
        req = ur.Request("https://example.com/a")
        fp, hdrs = io.BytesIO(), HTTPMessage()
        for target in ["http://127.0.0.1:631/", "ftp://example.com/f", "http://169.254.169.254/",
                       "http://０.０.０.０:631/", "http://127%2e0.0.1/", "http://%6cocalhost/",
                       "http://127.0.0.1%23@evil.example/"]:
            with self.subTest(target=target), self.assertRaises(net._Refused):
                h.redirect_request(req, fp, 302, "Found", hdrs, target)
        with mock.patch("urllib.request.getproxies", return_value={}), \
             mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 0))]):
            self.assertIsNotNone(h.redirect_request(req, fp, 302, "Found", hdrs, "https://example.com/b"))

    def test_refused_redirect_becomes_a_status_not_a_crash(self):
        with mock.patch.object(net, "_open", side_effect=net._Refused("refused: private address 10.0.0.1 (redirect)")):
            text, status = net.get("https://93.184.215.14/p")
        self.assertIsNone(text)
        self.assertIn("redirect", status)

    def run_daily(self, project: Path, skill: Path, host: str):
        import shutil, subprocess
        shutil.copytree(ROOT / "skills" / "what-changed", skill)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(project),
               "WHAT_CHANGED_HOST": host, "WHAT_CHANGED_PROJECT": str(project)}
        return subprocess.run(["bash", str(skill / "adapters" / "scheduler-cron" / "run-daily.sh")],
                              env=env, capture_output=True, text=True, timeout=60)

    def store_ran_today(self, project: Path):
        store = project / "uptodate"
        store.mkdir()
        (store / "runs.log").write_text(f"{date.today().isoformat()}T07:00:00+00:00\tscope=all\tdue=1/1\n", encoding="utf-8")
        import hashlib
        key = hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
        state = project / ".local" / "state" / "what-changed"  # run_daily() sets HOME to the project
        state.mkdir(parents=True)
        (state / f"{key}.last-run").write_text(date.today().isoformat() + "\n", encoding="utf-8")

    @POSIX_ONLY
    def test_other_hosts_refuse_a_skill_installed_in_the_project(self):
        for host in ["codex", "antigravity", "qwen"]:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as d:
                project = Path(d)
                self.store_ran_today(project)
                r = self.run_daily(project, project / ".agents" / "skills" / "what-changed", host)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("refusing", r.stderr)

    @POSIX_ONLY
    def test_skill_inside_uptodate_is_refused_for_claude_too(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            self.store_ran_today(project)
            r = self.run_daily(project, project / "uptodate" / "skills" / "what-changed", "claude")
            self.assertEqual(r.returncode, 2, r.stderr)

    @POSIX_ONLY
    def test_claude_and_outside_installs_pass_the_guard(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as home:
            project = Path(d)
            self.store_ran_today(project)
            r = self.run_daily(project, project / ".claude" / "skills" / "what-changed", "claude")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("already ran today", r.stdout)
            r = self.run_daily(project, Path(home) / "skills" / "what-changed", "codex")
            self.assertEqual(r.returncode, 0, r.stderr)

    @POSIX_ONLY
    def test_module_planted_in_project_is_not_imported(self):
        """No Python that run-daily starts outside the sandbox imports modules from the project or the store."""
        planted = []
        def plant(store):
            for folder in (store.parent, store):
                marker = folder / "PWNED"
                planted.append(marker)
                for name in ["json.py", "pathlib.py", "datetime.py", "argparse.py", "re.py"]:
                    (folder / name).write_text(f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8")
        r, lines, *_ = SchedulerSecurityTests.run_daily_with_fake_claude(self, prepare=plant)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(lines, "precheck and hosts.py must have run (claude was reached)")
        self.assertFalse([m for m in planted if m.exists()], "a module planted in the project was imported")


class _FakeSocket:
    """Records where a connection would go and refuses it, so no test touches the network."""
    connected: list = []

    def __init__(self, *a, **kw):
        pass

    def settimeout(self, t):
        pass

    def connect(self, sockaddr):
        _FakeSocket.connected.append(sockaddr)
        raise ConnectionRefusedError("test: no network")

    def close(self):
        pass


class SchedulerSecurityTests(unittest.TestCase):
    """Connections, allowlists, the scheduler's permissions, and writes that must not follow links."""

    def setUp(self):
        _FakeSocket.connected = []

    def test_dns_rebinding_is_caught_when_connecting(self):
        """The name resolves to a public address when checked and to a private one when
        urllib connects: the connection must use the checked lookup, not a second one."""
        answers = iter(["93.184.215.14"] + ["192.168.0.9"] * 10)
        def gai(host, port, *a, **kw):
            return [(2, 1, 6, "", (next(answers), port or 80))]
        with mock.patch("urllib.request.getproxies", return_value={}), \
             mock.patch("socket.getaddrinfo", side_effect=gai), \
             mock.patch("socket.socket", _FakeSocket), \
             mock.patch("socket.create_connection", side_effect=lambda addr, *a, **k: _FakeSocket().connect(addr)):
            text, status = net.get("http://rebind.example/", retries=0)
        self.assertIsNone(text)
        self.assertTrue(status.startswith("refused") and "private" in status, status)
        self.assertNotIn(("192.168.0.9", 80), _FakeSocket.connected)

    def test_connection_goes_to_the_checked_address(self):
        with mock.patch("urllib.request.getproxies", return_value={}), \
             mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 80))]), \
             mock.patch("socket.socket", _FakeSocket):
            net.get("http://public.example/", retries=0)
        self.assertEqual(_FakeSocket.connected, [("93.184.215.14", 80)])

    def test_proxied_requests_leave_the_name_to_the_proxy(self):
        import urllib.request as ur
        direct, via_https, via_http = ur.Request("https://a.example/"), ur.Request("https://a.example/"), ur.Request("http://a.example/")
        via_https.set_proxy("127.0.0.1:9", "https")
        via_http.set_proxy("127.0.0.1:9", "http")
        self.assertFalse(net._via_proxy(direct))
        self.assertTrue(net._via_proxy(via_https) and net._via_proxy(via_http))

    def test_hosts_never_lists_ip_addresses_or_local_names(self):
        """The host list is pasted into allowlists, so IPs and local names must not appear."""
        for url in ["http://127.0.0.1:8080/x", "http://[::1]/", "http://93.184.215.14/", "http://0x7f.1/",
                    "http://a.localhost/", "http://2130706433/", "http://192.168.1.1/admin"]:
            with self.subTest(url=url):
                self.assertIsNone(hosts._host(url))
        self.assertEqual(hosts._host("https://Docs.Example.com/x"), "docs.example.com")
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "topics.yaml").write_text(TOPICS.replace(
                "      - https://example.com/CHANGELOG.md", "      - https://example.com/CHANGELOG.md\n      - http://127.0.0.1:8080/x"), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                hosts.main(["hosts.py", "--store", str(store), "--comma"])
        self.assertEqual(out.getvalue().strip(), "example.com")

    def test_allowed_hosts_env_limits_every_fetch(self):
        """In unattended runs the scripts may fetch only the allowed hosts, so a
        prompt-injected agent cannot use fingerprint.py to send data elsewhere."""
        env = {"WHAT_CHANGED_ALLOWED_HOSTS": "example.com,*.example.org"}
        with mock.patch.dict(os.environ, env), mock.patch("urllib.request.getproxies", return_value={}), \
             mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 0))]):
            self.assertIsNone(net.refused("https://example.com/x"))
            self.assertIsNone(net.refused("https://docs.example.org/x"))
            for url in ["https://evil.example/?d=secret", "https://example.org/", "https://www.example.com/",
                        "https://example.com.evil.example/"]:
                with self.subTest(url=url):
                    self.assertIn("not in the allowed hosts", net.refused(url) or "")
            h = net._CheckedRedirect()
            import urllib.request as ur
            from http.client import HTTPMessage
            with self.assertRaises(net._Refused):
                h.redirect_request(ur.Request("https://example.com/a"), io.BytesIO(), 302, "Found", HTTPMessage(),
                                   "https://evil.example/b")
        for unrestricted in ({"WHAT_CHANGED_ALLOWED_HOSTS": "*"}, {}):
            with mock.patch.dict(os.environ, unrestricted, clear=False), \
                 mock.patch("urllib.request.getproxies", return_value={}), \
                 mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 0))]):
                os.environ.pop("WHAT_CHANGED_ALLOWED_HOSTS", None) if not unrestricted else None
                self.assertIsNone(net.refused("https://evil.example/"))

    def test_hosts_allow_merges_watchlist_and_user_domains(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")
            def allow(extra):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = hosts.main(["hosts.py", "--store", str(store), "--allow", extra])
                return code, out.getvalue().splitlines()
            self.assertEqual(allow(""), (0, ["example.com", "WebFetch(domain:example.com)"]))
            self.assertEqual(allow("Docs.Python.org, *.example.org,example.com"),
                             (0, ["example.com,docs.python.org,*.example.org",
                                  "WebFetch(domain:example.com),WebFetch(domain:docs.python.org),WebFetch(domain:*.example.org)"]))
            self.assertEqual(allow("*"), (0, ["*", "WebFetch"]))
            for bad in ["evil.com),Bash(*", "a b.com", "127.0.0.1", "*", "x.*.com", "localhost"]:
                if bad == "*":
                    continue
                with self.subTest(extra=bad):
                    self.assertEqual(allow(bad)[0], 2)

    def run_daily_with_fake_claude(self, extra_env=None, prepare=None):
        """run-daily.sh with a stand-in `claude` that records its folder, arguments and env."""
        import shutil, subprocess
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        project, home, bindir = Path(d) / "project", Path(d) / "home", Path(d) / "bin"
        store = project / "uptodate"
        store.mkdir(parents=True)
        bindir.mkdir()
        (project / "secret.env").write_text("TOKEN=x\n", encoding="utf-8")
        (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")  # no ledger yet: precheck exits 10
        if prepare:
            prepare(store)
        skill = home / "skills" / "what-changed"
        shutil.copytree(ROOT / "skills" / "what-changed", skill)
        record = Path(d) / "record.txt"
        fake = bindir / "claude"
        fake.write_text('#!/bin/sh\n[ "$1" = --version ] && [ -n "$FAKE_HANG" ] && sleep 30\n'
                        '[ "$1" = --version ] && { echo "${FAKE_VERSION:-2.1.300} (Claude Code)"; exit 0; }\n'
                        '[ -n "$FAKE_SILENT" ] || { mkdir -p digests; echo "# Digest" > "digests/$(date +%Y-%m-%d).md"; }\n'
                        '{ pwd -P; for a in "$@"; do printf "ARG %s\\n" "$a"; done; '
                        'env | grep "^WHAT_CHANGED_" | sort; echo "USER=$USER"; } > "$RECORD"\n'
                        '[ -n "$FAKE_FAIL" ] && { echo "{\\"result\\": \\"Not logged in\\"}"; exit 1; }\nexit 0\n',
                        encoding="utf-8")
        fake.chmod(0o755)
        env = {"PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}", "HOME": str(home), "RECORD": str(record),
               "WHAT_CHANGED_HOST": "claude", "WHAT_CHANGED_PROJECT": str(project),
               "WHAT_CHANGED_PYTHON": sys.executable, **(extra_env or {})}
        r = subprocess.run(["bash", str(skill / "adapters" / "scheduler-cron" / "run-daily.sh")],
                           env=env, capture_output=True, text=True, timeout=60)
        lines = record.read_text(encoding="utf-8").splitlines() if record.exists() else []
        tools = next((l.split(" ", 1)[1] for i, l in enumerate(lines) if i and lines[i - 1] == "ARG --allowedTools"), "")
        return r, lines, tools, store.resolve(), skill.resolve()

    @POSIX_ONLY
    def test_claude_runs_inside_the_store_with_narrow_rules(self):
        r, lines, tools, store, skill = self.run_daily_with_fake_claude()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(lines[0], str(store), "claude must start in uptodate/, not the project")
        rules = tools.split(",")
        self.assertIn("WebFetch(domain:example.com)", rules)
        self.assertNotIn("WebFetch", rules, "no unrestricted WebFetch by default")
        self.assertIn(f"Edit(/{store}/ledger/**)", rules)
        self.assertIn(f"Edit(/{store}/digests/**)", rules)
        self.assertNotIn(f"Edit(/{store}/runs.log)", rules, "runs.log lines come from log_run.py and the clock")
        self.assertIn(f"Bash({sys.executable} {skill}/scripts/log_run.py *)", rules)
        self.assertFalse([x for x in rules if x.startswith("Edit(") and ("topics" in x or x.endswith("uptodate/**)"))],
                         "topics.yaml must not be editable in unattended runs")
        self.assertIn(f"Read(/{skill}/**)", rules)
        self.assertIn("WHAT_CHANGED_ALLOWED_HOSTS=example.com", lines)
        self.assertTrue(any(l.startswith("ARG ") and f"{skill}/SKILL.md" in l for l in lines), "prompt names SKILL.md")
        # The user's own settings (a Bash sandbox auto-allows commands even in dontAsk) must not apply.
        self.assertIn("ARG --restricted", lines)
        self.assertIn("ARG --strict-mcp-config", lines)
        self.assertEqual(lines[lines.index("ARG --tools") + 1], "ARG Read,Edit,Write,Bash,WebFetch,WebSearch")
        self.assertEqual(lines[lines.index("ARG --add-dir") + 1], f"ARG {skill}")

    @POSIX_ONLY
    def test_scripts_refuse_paths_outside_the_store(self):
        """With WHAT_CHANGED_STORE set, check_ledger and verify_quotes read nothing outside
        it, so the agent cannot probe for files or list .md files elsewhere."""
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            store = write_store(Path(d) / "uptodate")
            (Path(other) / "notes.md").write_text("---\ntopic: private\n---\n", encoding="utf-8")
            (store / "ledger" / "link.md").symlink_to(Path(other) / "notes.md")
            outside = [other, str(Path(other) / "notes.md"), str(store / ".." / ".." / Path(other).name),
                       str(store / "ledger" / "link.md"), "/etc/hosts"]
            for main in (check_ledger.main, verify_quotes.main):
                for arg in outside:
                    with self.subTest(script=main.__module__, arg=arg), \
                         mock.patch.dict(os.environ, {"WHAT_CHANGED_STORE": str(store)}):
                        out = io.StringIO()
                        with redirect_stdout(out), mock.patch.object(verify_quotes, "fetch", side_effect=AssertionError):
                            self.assertEqual(main(["x", arg]), 2)
                        self.assertIn("outside the store", out.getvalue())
                        self.assertNotIn("notes.md", out.getvalue().replace(arg, ""))
            (store / "ledger" / "link.md").unlink()
            with mock.patch.dict(os.environ, {"WHAT_CHANGED_STORE": str(store)}), redirect_stdout(io.StringIO()):
                self.assertEqual(check_ledger.main(["x", str(store)]), 0)
                self.assertEqual(check_ledger.main(["x", str(store / "ledger" / "demo.md")]), 0)
        r, lines, *_rest = self.run_daily_with_fake_claude()
        self.assertIn(f"WHAT_CHANGED_STORE={_rest[1]}", lines)

    @POSIX_ONLY
    def test_scheduler_record_lives_outside_the_project(self):
        """Other hosts can write anywhere in the project, so the 'ran today' record must not be there."""
        r, lines, tools, store, skill = self.run_daily_with_fake_claude()
        self.assertEqual(r.returncode, 0, r.stderr)
        project, home = store.parent, store.parent.parent / "home"
        records = list((home / ".local" / "state" / "what-changed").glob("*.last-run"))
        self.assertEqual([x.read_text(encoding="utf-8").strip() for x in records], [date.today().isoformat()])
        self.assertFalse([x for x in project.rglob("*") if "done" in x.name or x.suffix == ".last-run"])
        prompt = next(l for l in lines if l.startswith("ARG Use the what-changed skill"))
        self.assertIn(f"{sys.executable} {skill}/scripts/check_ledger.py {store}", prompt)
        self.assertIn("Pages can be fetched only from: example.com", prompt)

    @POSIX_ONLY
    def test_runs_logged_in_advance_do_not_count(self):
        """The agent can write runs.log, so it could log tomorrow (or the next year) as done.
        A line dated today counts only if runs.log was written today."""
        import time
        today = date.today().isoformat()
        def planted(store):
            log = store / "runs.log"
            log.write_text(f"{today}T07:00:00+00:00\tscope=all\tdue=1/1\n", encoding="utf-8")
            yesterday = time.time() - 86400 - 3600
            os.utime(log, (yesterday, yesterday))
        def planted_then_written_today(store):
            planted(store)
            with (store / "runs.log").open("a", encoding="utf-8") as f:  # e.g. a manual one-topic run
                f.write(f"{today}T06:00:00+00:00\tscope=topics\tchecked=other\n")
        for prepare in (planted, planted_then_written_today):
            r, lines, *_ = self.run_daily_with_fake_claude(prepare=prepare)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("already ran today", r.stdout)
            self.assertTrue(lines, "the run must go ahead")
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            planted(store)
            self.assertFalse(catch_up.ran_today(store / "runs.log", today))
            buf = io.StringIO()
            with redirect_stdout(buf):
                precheck.main(["precheck.py", "--store", str(store), "--today", today])
            self.assertNotIn("already ran today", buf.getvalue())
            os.utime(store / "runs.log")  # written now: a real run today
            self.assertTrue(catch_up.ran_today(store / "runs.log", today))
            (store / "runs.log").write_text(f"{today}T07:00:00+00:00\tscope=all\n2099-01-01T07:00:00+00:00\tscope=all\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                precheck.main(["precheck.py", "--store", str(store), "--today", today])
            self.assertIn("dated after today", buf.getvalue())

    def test_precheck_after_a_same_day_run_writes_nothing(self):
        """After an agent run today (logged as scope=topics, so not 'today is done'), precheck
        writes nothing: no 'No change' section and no scope=all line."""
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "ledger").mkdir()
            (store / "digests").mkdir()
            (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")
            (store / "ledger" / "demo.md").write_text(DEMO_LEDGER.replace("last_run: 2026-10-14", "last_run: 2026-10-15"), encoding="utf-8")
            digest = "# Digest 2026-10-15\n\n## Run 09:00 (light)\n1. Version 2.1.297 is out\n"
            log = "2026-10-15T09:00:00+00:00\tscope=topics\tchecked=demo\tchanged=1\n"
            (store / "digests" / "2026-10-15.md").write_text(digest, encoding="utf-8")
            (store / "runs.log").write_text(log, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf), mock.patch.object(precheck, "fingerprint", side_effect=AssertionError("no fetch")):
                code = precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
            self.assertEqual(code, 0)
            self.assertIn("ran earlier today", buf.getvalue())
            self.assertEqual((store / "digests" / "2026-10-15.md").read_text(encoding="utf-8"), digest)
            self.assertEqual((store / "runs.log").read_text(encoding="utf-8"), log)
            (store / "ledger" / "demo.md").write_text(DEMO_LEDGER.replace("last_run: 2026-10-14", "last_run: 2099-01-01"), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), precheck.NEEDS_AGENT)

    def test_odd_ledger_files_do_not_stop_the_scheduler(self):
        """The agent can make ledger/x.md a folder (Write creates folders) or write a
        non-UTF-8 file; hosts.py --allow must skip such files, not stop the daily run."""
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")
            (store / "ledger" / "x.md").mkdir(parents=True)
            (store / "ledger" / "x.md" / "y").write_text("x", encoding="utf-8")
            (store / "ledger" / "bad.md").write_bytes(b"\xff\xfe\x00 not utf-8")
            out, err = io.StringIO(), io.StringIO()
            from contextlib import redirect_stderr
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(hosts.main(["hosts.py", "--store", str(store), "--allow", ""]), 0)
                self.assertEqual(hosts.main(["hosts.py", "--store", str(store)]), 0)
                check_ledger.main(["x", str(store)])
            self.assertEqual(out.getvalue().splitlines()[:2], ["example.com", "WebFetch(domain:example.com)"])

    def test_unreadable_topics_stop_the_run_loudly(self):
        """With topics.yaml unreadable, --allow must fail with a message, not return an empty
        list that would refuse every fetch while the run appears to succeed."""
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "topics.yaml").write_text("topics:\n  - id: demo\n    sources: [https://example.com/]\n  odd line\n", encoding="utf-8")
            err = io.StringIO()
            from contextlib import redirect_stderr
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(hosts.main(["hosts.py", "--store", str(store), "--allow", ""]), 2)
            self.assertIn("topics.yaml", err.getvalue())

    def test_more_ipv6_forms_of_local_addresses(self):
        for host in ["::7f00:1", "::ffff:0:7f00:1", "fec0::1", "::a00:1"]:
            with self.subTest(host=host):
                self.assertTrue(net._private_ip(__import__("ipaddress").ip_address(host)))
        self.assertIsNotNone(net.refused("http://[::7f00:1]/"))

    def test_next_address_is_tried_when_a_socket_cannot_be_made(self):
        """An IPv6 answer on a machine without IPv6: socket() itself fails; try the next answer."""
        made = []
        def fake_socket(family, *a, **kw):
            if family == socket.AF_INET6:  # its number differs by OS (30 macOS, 10 Linux, 23 Windows)
                raise OSError("address family not supported")
            made.append(family)
            return _FakeSocket()
        infos = [(socket.AF_INET6, 1, 6, "", ("2606:2800:21f:cb07:6820:80da:af6b:8b2c", 80, 0, 0)),
                 (socket.AF_INET, 1, 6, "", ("93.184.215.14", 80))]
        with mock.patch("socket.getaddrinfo", return_value=infos), mock.patch("socket.socket", side_effect=fake_socket):
            with self.assertRaises(ConnectionRefusedError):
                net._pinned_connection(("public.example", 80), 5)
        self.assertEqual(_FakeSocket.connected, [("93.184.215.14", 80)])

    def quiet_store(self, d):
        store = Path(d) / "uptodate"
        (store / "ledger").mkdir(parents=True)
        (store / "topics.yaml").write_text(TOPICS, encoding="utf-8")
        (store / "ledger" / "demo.md").write_text(DEMO_LEDGER, encoding="utf-8")
        (store / "runs.log").write_text("2026-10-14T07:00:00+00:00\tscope=all\tdue=1/1\n", encoding="utf-8")
        return store

    @NEEDS_SYMLINKS
    def test_precheck_never_writes_through_a_symlink(self):
        """Hosts other than claude can plant symlinks in the project; precheck runs
        outside any sandbox and must not append page titles to, say, ~/.zshrc."""
        fp = mock.patch.object(precheck, "fingerprint", return_value={
            "url": "u", "ok": True, "kind": "changelog", "fingerprint": "2.1.296", "detail": "", "partial": False})
        for planted in ("runs.log", "digests", "ledger/demo.md"):
            with self.subTest(planted=planted), tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
                store = self.quiet_store(d)
                victim = Path(outside) / "victim"
                if planted == "digests":
                    victim.mkdir()
                else:
                    victim.write_text((store / planted).read_text(encoding="utf-8") if (store / planted).exists() else "x", encoding="utf-8")
                before = sorted(p.name for p in Path(outside).rglob("*")), victim.is_file() and victim.read_text(encoding="utf-8")
                target = store / planted
                if target.exists():
                    target.unlink()
                target.symlink_to(victim, target_is_directory=victim.is_dir())
                buf = io.StringIO()
                with fp, redirect_stdout(buf):
                    code = precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
                self.assertEqual(code, 2, buf.getvalue())
                self.assertIn("symlink", buf.getvalue())
                after = sorted(p.name for p in Path(outside).rglob("*")), victim.is_file() and victim.read_text(encoding="utf-8")
                self.assertEqual(before, after, "something was written outside the store")

    @NEEDS_SYMLINKS
    def test_no_write_through_hardlinks_or_the_catch_up_marker(self):
        """A hard link (runs.log sharing ~/.zshrc's inode) and the session hook's marker
        file are write paths too."""
        fp = mock.patch.object(precheck, "fingerprint", return_value={
            "url": "u", "ok": True, "kind": "changelog", "fingerprint": "2.1.296", "detail": "", "partial": False})
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            store = self.quiet_store(d)
            victim = Path(outside) / "victim"
            victim.write_text("keep\n", encoding="utf-8")
            (store / "runs.log").unlink()
            os.link(victim, store / "runs.log")
            buf = io.StringIO()
            with fp, redirect_stdout(buf):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), 2)
            self.assertIn("link", buf.getvalue())
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((store / "digests").exists(), "nothing may be written before the refusal")
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            store = Path(d)
            victim = Path(outside) / "victim"
            victim.write_text("keep\n", encoding="utf-8")
            (store / ".catchup-notified").symlink_to(victim)
            with mock.patch.object(sys, "argv", ["catch_up.py", "--store", str(store)]), redirect_stdout(io.StringIO()):
                catch_up.main()
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")

    @POSIX_ONLY
    def test_open_in_store_refuses_links_swapped_in_after_the_check(self):
        from ledger import UnsafeWrite, open_in_store
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            store, victim = Path(d), Path(outside) / "victim"
            victim.write_text("keep\n", encoding="utf-8")
            (store / "digests").symlink_to(outside)
            with self.assertRaises(UnsafeWrite):
                open_in_store(store, store / "digests" / "victim", append=True)
            os.link(victim, store / "runs.log")
            with self.assertRaises(UnsafeWrite):
                open_in_store(store, store / "runs.log", append=False)  # must not truncate first
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")
            with open_in_store(store, store / "ledger" / "new.md", append=False) as f:
                f.write("ok")
            self.assertEqual((store / "ledger" / "new.md").read_text(encoding="utf-8"), "ok")

    @POSIX_ONLY
    def test_a_fifo_does_not_hang_the_hook(self):
        """An agent could mkfifo the marker; opening a FIFO for writing blocks forever."""
        import signal
        from ledger import UnsafeWrite, open_in_store
        def timeout(*a):  # not an OSError, so nothing on the way can swallow it
            raise RuntimeError("open blocked on a FIFO")
        old = signal.signal(signal.SIGALRM, timeout)
        signal.alarm(5)
        try:
            with tempfile.TemporaryDirectory() as d:
                store = Path(d)
                os.mkfifo(store / ".catchup-notified")
                with self.assertRaises(UnsafeWrite):
                    open_in_store(store, store / ".catchup-notified", append=False)
                with mock.patch.object(sys, "argv", ["catch_up.py", "--store", str(store)]), redirect_stdout(io.StringIO()):
                    self.assertEqual(catch_up.main(), 0)
                with self.assertRaises(UnsafeWrite):
                    open_in_store(store, store, append=True)  # no file name at all
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    @POSIX_ONLY
    def test_run_logs_live_outside_the_project_and_symlinked_store_is_refused(self):
        r, lines, tools, store, skill = self.run_daily_with_fake_claude()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((store.parent / ".what-changed-logs").exists())
        logs = list((store.parent.parent / "home" / ".local" / "state" / "what-changed").glob("*/*-precheck.out"))
        self.assertEqual(len(logs), 1)
        import shutil, subprocess
        with tempfile.TemporaryDirectory() as d:
            project, home, real = Path(d) / "project", Path(d) / "home", Path(d) / "elsewhere"
            project.mkdir(); real.mkdir(); (home / "bin").mkdir(parents=True)
            (project / "uptodate").symlink_to(real)
            fake = home / "bin" / "codex"
            fake.write_text("#!/bin/sh\ntouch \"$HOME/CODEX_RAN\"\n", encoding="utf-8")
            fake.chmod(0o755)
            shutil.copytree(ROOT / "skills" / "what-changed", home / "skills" / "what-changed")
            env = {"PATH": f"{home / 'bin'}:/usr/bin:/bin", "HOME": str(home),
                   "WHAT_CHANGED_HOST": "codex", "WHAT_CHANGED_PROJECT": str(project)}
            r = subprocess.run(["bash", str(home / "skills" / "what-changed" / "adapters" / "scheduler-cron" / "run-daily.sh")],
                               env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("symlink", r.stderr)
            self.assertFalse((home / "CODEX_RAN").exists())

    @POSIX_ONLY
    def test_user_domains_and_opt_out(self):
        r, lines, tools, *_ = self.run_daily_with_fake_claude({"WHAT_CHANGED_FETCH_DOMAINS": "docs.python.org"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WebFetch(domain:docs.python.org)", tools.split(","))
        self.assertIn("WHAT_CHANGED_ALLOWED_HOSTS=example.com,docs.python.org", lines)
        r, lines, tools, *_ = self.run_daily_with_fake_claude({"WHAT_CHANGED_FETCH_DOMAINS": "*"})
        self.assertIn("WebFetch", tools.split(","))
        self.assertIn("WHAT_CHANGED_ALLOWED_HOSTS=*", lines)
        r, lines, tools, *_ = self.run_daily_with_fake_claude({"WHAT_CHANGED_FETCH_DOMAINS": "evil.com),Bash(*"})
        self.assertEqual(r.returncode, 2)
        self.assertEqual(lines, [], "claude must not start with a bad domain list")


class RunLoggingTests(unittest.TestCase):
    """Unreachable sources, run times from the clock, and how the scheduler finds and checks the agent CLI."""

    def store(self, d: str) -> Path:
        return PrecheckTests.make_store(self, d)

    def failing(self, detail="blocked-local (blocked by a local proxy or sandbox, not the site: allow this host: example.com)"):
        return mock.patch.object(precheck, "fingerprint", return_value={
            "url": "u", "ok": False, "kind": None, "fingerprint": None, "partial": False, "detail": detail})

    def test_no_reachable_source_is_could_not_check_not_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.store(d)
            buf = io.StringIO()
            with self.failing(), redirect_stdout(buf):
                code = precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"])
            self.assertEqual(code, precheck.COULD_NOT_CHECK)
            self.assertIn("not counted as done", buf.getvalue())
            digest = (store / "digests" / "2026-10-15.md").read_text(encoding="utf-8")
            self.assertIn("— Could not check", digest)
            self.assertNotIn("No change", digest)
            self.assertNotIn("fingerprints unchanged", digest)
            self.assertIn("topics checked 0/1", digest)
            ledger = (store / "ledger" / "demo.md").read_text(encoding="utf-8")
            self.assertIn("last_run: 2026-10-14", ledger)  # not counted as checked
            self.assertIn("— failed (1 in a row): blocked-local", ledger)
            log = (store / "runs.log").read_text(encoding="utf-8").splitlines()
            self.assertFalse([l for l in log if l.startswith("2026-10-15") and "scope=all" in l])
            self.assertNotIn("2026-10-15", catch_up.daily_run_dates(store / "runs.log"))
            with self.failing("TimeoutError"), redirect_stdout(io.StringIO()):  # tried again, not skipped
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]),
                                 precheck.COULD_NOT_CHECK)
            with PrecheckTests.fp(self, "2.1.296"), redirect_stdout(io.StringIO()):  # reachable again: done
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), 0)
            self.assertIn("2026-10-15", catch_up.daily_run_dates(store / "runs.log"))

    def test_one_dead_topic_does_not_keep_every_day_open(self):
        """The other topics were checked, so the day is done; the dead topic stays due, and after
        3 failed runs in a row its source is marked possibly gone."""
        with tempfile.TemporaryDirectory() as d:
            store = self.store(d)
            (store / "topics.yaml").write_text(TOPICS + TOPICS.split("\n", 1)[1].replace("id: demo", "id: other")
                                               .replace("example.com", "example.org"), encoding="utf-8")
            (store / "ledger" / "other.md").write_text(DEMO_LEDGER.replace("demo", "other").replace("example.com", "example.org"),
                                                       encoding="utf-8")
            ok = {"url": "u", "ok": True, "kind": "changelog", "fingerprint": "2.1.296", "detail": "", "partial": False}
            bad = {"url": "u", "ok": False, "kind": None, "fingerprint": None, "partial": False, "detail": "HTTP 503"}
            with mock.patch.object(precheck, "fingerprint", side_effect=lambda url, t: ok if "example.com" in url else bad), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]), 0)
            digest = (store / "digests" / "2026-10-15.md").read_text(encoding="utf-8")
            self.assertIn("— No change in 1 topic(s); could not check 1", digest)
            self.assertIn("[demo] fingerprints unchanged", digest)
            self.assertIn("[other] could not check any source", digest)
            self.assertIn("[other] https://example.org/CHANGELOG.md — HTTP 503 (failed 1 run(s) in a row)", digest)
            self.assertIn("last_run: 2026-10-15", (store / "ledger" / "demo.md").read_text(encoding="utf-8"))
            self.assertIn("last_run: 2026-10-14", (store / "ledger" / "other.md").read_text(encoding="utf-8"))
            self.assertIn("scope=all", (store / "runs.log").read_text(encoding="utf-8").splitlines()[-1])
            for day in ("2026-10-16", "2026-10-17"):
                with mock.patch.object(precheck, "fingerprint", side_effect=lambda url, t: ok if "example.com" in url else bad), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", day]), 0)
            digest = (store / "digests" / "2026-10-17.md").read_text(encoding="utf-8")
            self.assertIn("(failed 3 run(s) in a row) — possibly gone", digest)
            self.assertIn("— failed (3 in a row): HTTP 503", (store / "ledger" / "other.md").read_text(encoding="utf-8"))
            with PrecheckTests.fp(self, "2.1.296"), redirect_stdout(io.StringIO()):  # back again: counter cleared
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-18"]), 0)
            other = (store / "ledger" / "other.md").read_text(encoding="utf-8")
            self.assertIn("checked: 2026-10-18 — ok", other)
            self.assertNotIn("in a row", other)

    def test_log_run_stamps_lines_from_the_clock(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.store(d)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(log_run.main(["log_run.py", "--now"]), 0)
            iso, hhmm = out.getvalue().split()
            started = datetime.fromisoformat(iso)
            self.assertLess(abs((datetime.now().astimezone() - started).total_seconds()), 5)
            self.assertEqual(hhmm, f"{started:%H:%M}")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(log_run.main(["log_run.py", "--store", str(store), "--started", iso,
                                               "scope=all", "mode=demo:light", "host=test", "due=1/1"]), 0)
            last = (store / "runs.log").read_text(encoding="utf-8").splitlines()[-1].split("\t")
            self.assertEqual(last[0], iso)
            self.assertEqual(last[1:], ["scope=all", "mode=demo:light", "host=test", "due=1/1"])
            future = (datetime.now().astimezone() + timedelta(minutes=13)).isoformat(timespec="seconds")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(log_run.main(["log_run.py", "--store", str(store), "--started", future, "scope=topics"]), 0)
            self.assertIn("in the future", out.getvalue())
            stamp = datetime.fromisoformat((store / "runs.log").read_text(encoding="utf-8").splitlines()[-1].split("\t")[0])
            self.assertLessEqual(stamp, datetime.now().astimezone())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(log_run.main(["log_run.py", "--store", str(store), "mode=x"]), 2)  # no scope
                self.assertEqual(log_run.main(["log_run.py", "--store", str(store), "scope=all", "bad\tfield"]), 2)
            with tempfile.TemporaryDirectory() as other, mock.patch.dict(os.environ, {"WHAT_CHANGED_STORE": other}), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(log_run.main(["log_run.py", "--store", str(store), "scope=all"]), 2)

    def test_check_ledger_flags_run_times_later_than_the_files(self):
        """A run time later than the file was written (made up, not read from the clock) is caught; real ones pass."""
        import time
        with tempfile.TemporaryDirectory() as d:
            store = self.store(d)
            now = datetime.now().astimezone().replace(microsecond=0)
            today = now.date().isoformat()
            later = now + timedelta(minutes=13)
            (store / "digests").mkdir()
            digest = store / "digests" / f"{today}.md"
            digest.write_text(f"# Digest {today}\n\n## Run {now:%H:%M} (light)\n- ok\n", encoding="utf-8")
            with open(store / "runs.log", "a", encoding="utf-8") as f:
                f.write(f"{now.isoformat()}\tscope=all\tdue=1/1\n")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(check_ledger.main(["x", str(store)]), 0, out.getvalue())
            self.assertIn("run times are not later than the file was written", out.getvalue())
            if later.date() != now.date():
                self.skipTest("too close to midnight to place a later time on the same day")
            with open(store / "runs.log", "a", encoding="utf-8") as f:
                f.write(f"{later.isoformat()}\tscope=topics\tdue=1/1\n")
            with open(digest, "a", encoding="utf-8") as f:
                f.write(f"\n## Run {later:%H:%M} (full)\n- made up\n")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(check_ledger.main(["x", str(store)]), 1)
            self.assertIn("runs.log:3", out.getvalue())
            self.assertIn(f"Run {later:%H:%M} is after the file was last written", out.getvalue())
            old = time.time() - 86400 * 3  # a digest from another day: HH:MM alone is not compared
            os.utime(digest, (old, old))
            os.utime(store / "runs.log", (time.time(), time.time()))

    @POSIX_ONLY
    def test_scheduler_stops_loudly_on_an_old_or_missing_claude(self):
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self, extra_env={"FAKE_VERSION": "2.1.81"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("2.1.81", r.stderr)
        self.assertIn("2.1.248 or later", r.stderr)
        self.assertEqual(lines, [], "claude -p must not be started")
        store = _rest[1]
        home = store.parent.parent / "home"
        errors = list((home / ".local" / "state" / "what-changed").glob("*/*-error.txt"))
        self.assertEqual(len(errors), 1)
        self.assertIn("2.1.81", errors[0].read_text(encoding="utf-8"))
        self.assertFalse(list((home / ".local" / "state" / "what-changed").glob("*.last-run")), "day must stay open")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(home / ".local" / "state")}):
            self.assertIn("2.1.81", catch_up.message(store, None, False, catch_up.scheduler_error(store, date.today().isoformat())))
        r, lines, *_ = SchedulerSecurityTests.run_daily_with_fake_claude(
            self, extra_env={"WHAT_CHANGED_CLAUDE": "/nonexistent/claude"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("claude not found", r.stderr)

    @POSIX_ONLY
    def test_scheduler_finds_claude_in_local_bin_first(self):
        """The installer puts claude in ~/.local/bin, which cron and launchd leave off PATH."""
        def install(store):
            home = store.parent.parent / "home"
            (home / ".local" / "bin").mkdir(parents=True)
            fake = home / ".local" / "bin" / "claude"
            fake.write_text('#!/bin/sh\n[ "$1" = --version ] && { echo "2.1.300 (Claude Code)"; exit 0; }\n'
                            'pwd -P > "$RECORD.local"; mkdir -p digests; echo "# Digest" > "digests/$(date +%Y-%m-%d).md"\n',
                            encoding="utf-8")
            fake.chmod(0o755)
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self, extra_env={"FAKE_VERSION": "2.1.81"},
                                                                             prepare=install)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(lines, [], "the old claude further down PATH must not run")
        record = Path(str(_rest[1].parent.parent / "record.txt") + ".local")
        self.assertTrue(record.exists(), "the ~/.local/bin claude ran")

    @POSIX_ONLY
    def test_scheduler_does_not_count_an_unreachable_day(self):
        def offline(store):
            (store / "ledger").mkdir()
            (store / "ledger" / "demo.md").write_text(DEMO_LEDGER.replace("2026-10-14", "2026-01-01"), encoding="utf-8")
            (store / "topics.yaml").write_text(TOPICS.replace("https://example.com/", "http://127.0.0.1:9/"), encoding="utf-8")
            p = store / "ledger" / "demo.md"
            p.write_text(p.read_text(encoding="utf-8").replace("https://example.com/", "http://127.0.0.1:9/"), encoding="utf-8")
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self, prepare=offline)
        self.assertEqual(r.returncode, 11, r.stdout + r.stderr)
        self.assertEqual(lines, [], "the agent is not started when nothing can be fetched")
        home = _rest[1].parent.parent / "home"
        self.assertFalse(list((home / ".local" / "state" / "what-changed").glob("*.last-run")))

    def test_writes_work_without_posix_only_flags(self):
        """Windows has no O_NOFOLLOW, O_NONBLOCK or dir_fd; open_in_store falls back to checks by path."""
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            with mock.patch.object(ledger, "_NOFOLLOW", 0), mock.patch.object(ledger, "_NONBLOCK", 0), \
                 mock.patch.object(os, "supports_dir_fd", set()):
                with ledger.open_in_store(store, store / "digests" / "x.md", append=True) as f:
                    f.write("a\n")
                with ledger.open_in_store(store, store / "digests" / "x.md", append=True) as f:
                    f.write("b\n")
                self.assertEqual((store / "digests" / "x.md").read_bytes(), b"a\nb\n")
                (store / "real.md").write_text("x", encoding="utf-8")
                try:
                    (store / "link.md").symlink_to(store / "real.md")
                except OSError:  # Windows without the right to make symlinks
                    return
                with self.assertRaises(ledger.UnsafeWrite):
                    ledger.open_in_store(store, store / "link.md", append=True)

    @POSIX_ONLY
    def test_scheduler_logs_a_run_the_agent_did_not_log_and_keeps_a_day_without_digest_open(self):
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self)
        self.assertEqual(r.returncode, 0, r.stderr)
        store = _rest[1]
        last = (store / "runs.log").read_text(encoding="utf-8").splitlines()[-1]
        self.assertIn("scope=all", last)
        self.assertIn("logged_by=scheduler", last)
        self.assertTrue(last.startswith(date.today().isoformat()))
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self, extra_env={"FAKE_SILENT": "1"})
        self.assertEqual(r.returncode, 5)
        self.assertIn("without writing today's digest", r.stderr)
        home = _rest[1].parent.parent / "home"
        self.assertFalse(list((home / ".local" / "state" / "what-changed").glob("*.last-run")))

    def test_log_run_rejects_line_breaks_and_compares_days_in_local_time(self):
        self.assertIsNone(log_run.FIELD.fullmatch("a=b\n"))
        clock = datetime(2026, 10, 16, 6, 0, tzinfo=timezone(timedelta(hours=7)))
        stamp, why = log_run.run_start("2026-10-15T23:30:00+00:00", clock)  # 06:30 local: future
        self.assertIsNotNone(why)
        stamp, why = log_run.run_start("2026-10-15T22:30:00+00:00", clock)  # 05:30 local, same day
        self.assertIsNone(why)
        self.assertEqual(stamp.utcoffset(), timedelta(hours=7))

    def test_cli_version_check_has_a_time_limit(self):
        import time
        d = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, d, True)
        windows = os.name == "nt"
        def cli(posix: str, batch: str) -> str:
            path = d / f"cli{len(list(d.iterdir()))}{'.bat' if windows else ''}"
            path.write_text("@echo off\r\n" + batch + "\r\n" if windows else "#!/bin/sh\n" + posix + "\n", encoding="utf-8")
            path.chmod(0o755)
            return str(path)
        self.assertEqual(cli_version.check(cli('echo "2.1.300 (Claude Code)"', "echo 2.1.300 (Claude Code)"), "2.1.248", 5),
                         (0, "2.1.300"))
        self.assertEqual(cli_version.check(cli('echo "2.1.81 (Claude Code)"', "echo 2.1.81 (Claude Code)"), "2.1.248", 5)[0], 3)
        self.assertEqual(cli_version.check(cli("echo hello", "echo hello"), "2.1.248", 5)[0], 3)
        self.assertEqual(cli_version.check(str(d / "missing"), "2.1.248", 5)[0], 3)
        began = time.monotonic()
        code, why = cli_version.check(cli("sleep 30 & sleep 30", "ping -n 30 127.0.0.1 >nul"), "2.1.248", 1)  # a child keeps running too
        self.assertEqual(code, 4)
        self.assertIn("did not answer within 1 seconds", why)
        self.assertLess(time.monotonic() - began, 10)

    @POSIX_ONLY
    def test_scheduler_stops_when_claude_version_hangs(self):
        import time
        began = time.monotonic()
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(
            self, extra_env={"FAKE_HANG": "1", "WHAT_CHANGED_VERSION_TIMEOUT": "1"})
        self.assertLess(time.monotonic() - began, 20)
        self.assertEqual(r.returncode, 3)
        self.assertIn("did not answer within 1 seconds", r.stderr)
        self.assertEqual(lines, [], "claude -p must not be started")
        home = _rest[1].parent.parent / "home"
        errors = list((home / ".local" / "state" / "what-changed").glob("*/*-error.txt"))
        self.assertIn("did not answer", errors[0].read_text(encoding="utf-8"))
        self.assertFalse(list((home / ".local" / "state" / "what-changed").glob("*.last-run")))

    def test_fingerprint_not_made_by_the_script_asks_for_a_baseline(self):
        """An agent that could not run fingerprint.py may store a date or a sentence; that is not
        a change of the source."""
        self.assertTrue(precheck.made_by_script("PEP 745 | PEP 745 – Python 3.14 | 6024cc2e6877", "page"))
        self.assertFalse(precheck.made_by_script("3.14.0 final: Tuesday, 2025-10-07", "page"))
        self.assertTrue(precheck.made_by_script("2.1.296", "changelog"))
        self.assertFalse(precheck.made_by_script("2026-10-09 | v2.1.296 | extra words here and there and more", "changelog"))
        with tempfile.TemporaryDirectory() as d:
            store = self.store(d)
            p = store / "ledger" / "demo.md"
            p.write_text(p.read_text(encoding="utf-8").replace('fingerprint: "2.1.296"', 'fingerprint: "3.14.0 final: Tuesday"'),
                         encoding="utf-8")
            page = {"url": "u", "ok": True, "kind": "page", "fingerprint": "T | H | 6024cc2e6877", "detail": "", "partial": False}
            buf = io.StringIO()
            with mock.patch.object(precheck, "fingerprint", return_value=page), redirect_stdout(buf):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--today", "2026-10-15"]),
                                 precheck.NEEDS_AGENT)
            self.assertIn("was not made by fingerprint.py", buf.getvalue())
            self.assertNotIn("source changed", buf.getvalue())

    def test_list_sources(self):
        with tempfile.TemporaryDirectory() as d:
            store = self.store(d)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(precheck.main(["precheck.py", "--store", str(store), "--list-sources"]), 0)
            self.assertEqual(buf.getvalue().split(), ["https://example.com/CHANGELOG.md"])

    @POSIX_ONLY
    def test_scheduler_sets_user_and_reports_why_claude_failed(self):
        import getpass
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self)  # the test env has no USER
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"USER={getpass.getuser()}", lines)
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self, extra_env={"FAKE_FAIL": "1"})
        self.assertEqual(r.returncode, 4)
        self.assertIn("claude said: Not logged in", r.stderr)  # shown to the person reading the log
        home = _rest[1].parent.parent / "home"
        errors = list((home / ".local" / "state" / "what-changed").glob("*/*-error.txt"))
        text = errors[0].read_text(encoding="utf-8")
        self.assertIn("claude exited with an error; see", text)
        self.assertNotIn("Not logged in", text, "model text must not reach the file the hook reads")

    @POSIX_ONLY
    def test_scheduler_refusals_are_recorded_for_the_hook(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d)
            (project / "uptodate").mkdir()
            r = SecurityTests.run_daily(self, project, project / ".agents" / "skills" / "what-changed", "codex")
            self.assertEqual(r.returncode, 2)
            errors = list((project / ".local" / "state" / "what-changed").glob("*/*-error.txt"))
            self.assertEqual(len(errors), 1)
            self.assertIn("refusing: host codex can write anywhere", errors[0].read_text(encoding="utf-8"))


    @POSIX_ONLY
    def test_scheduler_refuses_a_python_older_than_3_11(self):
        """launchd and cron may find the python3 that comes with macOS (3.9)."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, d, True)
        old = d / "python3"
        old.write_text('#!/bin/sh\nexit 1\n', encoding="utf-8")  # fails the version check, as 3.9 would
        old.chmod(0o755)
        r, lines, *_rest = SchedulerSecurityTests.run_daily_with_fake_claude(self, extra_env={"WHAT_CHANGED_PYTHON": str(old)})
        self.assertEqual(r.returncode, 2)
        self.assertIn("is not Python 3.11 or later", r.stderr)
        self.assertEqual(lines, [], "claude must not be started")
        home = _rest[1].parent.parent / "home"
        errors = list((home / ".local" / "state" / "what-changed").glob("*/*-error.txt"))
        self.assertIn("not Python 3.11 or later", errors[0].read_text(encoding="utf-8"))
        # The error file is found where the hook looks for it: the key is the same without Python.
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(home / ".local" / "state")}):
            self.assertIn("3.11", catch_up.scheduler_error(_rest[1], date.today().isoformat()))

    def test_scripts_stop_with_a_clear_message_on_old_python(self):
        import subprocess
        for name in ("precheck.py", "check_ledger.py", "log_run.py", "catch_up.py", "fingerprint.py",
                     "hosts.py", "verify_quotes.py", "cli_version.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertIn("if sys.version_info < (3, 11):", text)
                guard = text.index("if sys.version_info < (3, 11):")
                self.assertLess(guard, text.find("sys.path.insert") if "sys.path.insert" in text else len(text),
                                "the check must run before the skill's own modules are imported")



class PluginManifestTests(unittest.TestCase):
    """The repository loads as a Claude Code plugin; its manifest must agree with the skill."""

    def test_plugin_manifest_matches_the_skill(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        skill = (ROOT / "skills" / "what-changed" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(manifest["name"], "what-changed")
        self.assertIn(f"name: {manifest['name']}\n", skill)
        self.assertIn(f'version: "{manifest["version"]}"', skill)
        self.assertEqual(manifest["license"], "MIT")
        for key in ("skills", "hooks", "mcpServers", "commands", "agents"):
            self.assertNotIn(key, manifest, "the plugin adds the skill only; hooks stay opt-in (adapters/)")
        self.assertFalse((ROOT / "hooks").exists(), "a hooks/ folder at the root would load as plugin hooks")

    def test_marketplace_lists_this_repository_under_the_manifest_name(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(market["plugins"], [{"name": manifest["name"], "source": "./"}])
        self.assertEqual(market["name"], "what-changed")  # the README's install commands use it


if __name__ == "__main__":
    unittest.main()
