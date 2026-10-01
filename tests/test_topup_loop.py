#!/usr/bin/env python3
"""episode_topup.py — the render-floor repair loop the external/claude engines lacked.

Four episodes died at voice.py's word floor (09-25, 09-27, 10-01 — logged four times
since 09-25, built on 10-01). These lock the properties that make the loop a fix rather
than a second way to lose the day:

  1. It measures with voice.py's parse_script(), never `wc -w`. The tag-counting
     discrepancy is real and measured (09-27: `wc -w` 6,040 vs 5,968 actual), so a loop
     that "verified" with wc -w would stop short of the floor it is trying to reach.
  2. A repair can never SHRINK the script.
  3. It only offers sources today's write passes did not already inline.
  4. It is bounded, and exhausting the budget fails loudly rather than shipping a stub.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import or_writer  # noqa: E402
import episode_topup  # noqa: E402


def block(speaker, words):
    return f"[{speaker}] " + " ".join(f"w{i}" for i in range(words))


def write_script(text):
    """A real temp script path (parse_script opens by path, so it can't be a StringIO)."""
    fd, name = tempfile.mkstemp(suffix=".txt")
    with open(fd, "w") as f:
        f.write(text)
    return Path(name)


def empty_sources():
    """A stand-in for or_writer._gather_sources()'s dict — every key _sources_block reads."""
    return {
        "topic_brief": "brief", "claude_md": "guide", "build_pitches": "",
        "transcripts": [], "articles": [], "recent_scripts": [], "covered": [],
        "evidence_rules": "rules", "evidence_ledger": "ledger", "aired_digest": "",
    }


class TestMeasurement(unittest.TestCase):
    """The floor check must be voice.py's own count, not the shell's."""

    def test_matches_voice_py_not_wc_w(self):
        script = "\n".join([
            block("BASIL", 600),
            "[TRANSITION]",
            block("BROOKE", 600),
            "[TRANSITION]",
        ])
        path = write_script(script)
        try:
            counted = episode_topup.speech_words(path)
            wc = len(script.split())
        finally:
            path.unlink()
        self.assertEqual(counted, 1200)
        # wc -w adds the 2 speaker tags + 2 [TRANSITION]s — this is exactly the overcount
        # that made a 5,968-word script look like it had cleared a 6,000-word floor.
        self.assertEqual(wc - counted, 4)

    def test_transition_segments_are_not_speech(self):
        path = write_script("[TRANSITION]\n\n" + block("BASIL", 10))
        try:
            self.assertEqual(episode_topup.speech_words(path), 10)
        finally:
            path.unlink()


class TestAntiShrink(unittest.TestCase):
    def test_a_shrinking_dispatch_is_discarded(self):
        """A 'repair' that deletes below the floor was the 06-21 Gemini outage."""
        path = write_script("\n".join([block("BASIL", 100), block("BROOKE", 100)]))
        before = path.read_text()
        try:
            def shrink(prompt, mode, script_path):
                script_path.write_text(block("BASIL", 5))      # catastrophic "repair"
                return ""

            with mock.patch.object(episode_topup, "_dispatch", shrink), \
                 mock.patch.object(episode_topup, "_unused_sources", return_value=([], [], 0)), \
                 mock.patch.object(episode_topup, "_write_pass_sources", empty_sources):
                rc = episode_topup.top_up(path, "external", "test", 1, 6000)
            self.assertEqual(rc, 1)
            self.assertEqual(path.read_text(), before)
        finally:
            path.unlink()


class TestUnusedSources(unittest.TestCase):
    def _tmp_with_sources(self):
        td = tempfile.TemporaryDirectory()
        tmp = Path(td.name) / ".tmp"
        (tmp / "transcripts").mkdir(parents=True)
        (tmp / "articles").mkdir(parents=True)
        (tmp / "transcripts" / "a.txt").write_text("x" * 5000)
        (tmp / "transcripts" / "b.txt").write_text("x" * 5000)
        (tmp / "articles" / "c.txt").write_text("x" * 5000)
        return td, tmp

    def test_already_offered_files_are_not_re_offered(self):
        td, tmp = self._tmp_with_sources()
        try:
            with mock.patch.object(or_writer, "TMP", tmp):
                t, a, pool = episode_topup._unused_sources({"a.txt"})
                self.assertEqual([p.name for p in t], ["b.txt"])
                self.assertEqual([p.name for p in a], ["c.txt"])
                self.assertEqual(pool, 2)
        finally:
            td.cleanup()

    def test_failed_fetch_stubs_are_excluded(self):
        """A 12-byte 'Music!' transcript is not evidence; it must not displace a real one."""
        td = tempfile.TemporaryDirectory()
        tmp = Path(td.name) / ".tmp"
        (tmp / "transcripts").mkdir(parents=True)
        (tmp / "articles").mkdir(parents=True)
        (tmp / "transcripts" / "stub.txt").write_text("Music!")
        (tmp / "transcripts" / "real.txt").write_text("x" * 5000)
        try:
            with mock.patch.object(or_writer, "TMP", tmp):
                t, _, _ = episode_topup._unused_sources(set())
                self.assertEqual([p.name for p in t], ["real.txt"])
        finally:
            td.cleanup()


class TestPrompt(unittest.TestCase):
    def test_the_model_is_told_the_exact_shortfall_and_the_floor(self):
        p = episode_topup.build_prompt(
            empty_sources(), current=4084, shortfall=1916, target=4232,
            openers="  · already covered thing", for_claude=False,
            script_path=Path("/tmp/x.txt"))
        self.assertIn("1,916", p)              # the exact shortfall
        self.assertIn("4,084", p)              # where it is now
        self.assertIn("4,232", p)              # what it must write
        self.assertIn("6,000", p)              # voice.py's floor
        self.assertIn("APPEND ONLY", p)
        self.assertIn("already covered thing", p)

    def test_claude_mode_is_told_to_append_to_the_file_not_replace_it(self):
        p = episode_topup.build_prompt(
            empty_sources(), current=10, shortfall=20, target=40, openers="",
            for_claude=True, script_path=Path("/tmp/x.txt"))
        self.assertIn("/tmp/x.txt", p)
        self.assertIn("Edit tool", p)
        self.assertIn("only ever grow", p)

    def test_external_mode_is_told_to_output_text_only(self):
        p = episode_topup.build_prompt(
            empty_sources(), current=10, shortfall=20, target=40, openers="",
            for_claude=False, script_path=Path("/tmp/x.txt"))
        self.assertIn("Output ONLY the new script blocks", p)


class TestBounded(unittest.TestCase):
    def test_loop_stops_as_soon_as_the_floor_is_met(self):
        path = write_script(block("BASIL", 50))
        calls = []
        try:
            def good(prompt, mode, script_path):
                calls.append(1)
                with open(script_path, "a") as fh:
                    fh.write("\n[TRANSITION]\n" + block("BROOKE", 100))
                return ""

            with mock.patch.object(episode_topup, "_dispatch", good), \
                 mock.patch.object(episode_topup, "_unused_sources", return_value=([], [], 0)), \
                 mock.patch.object(episode_topup, "_write_pass_sources", empty_sources):
                rc = episode_topup.top_up(path, "claude", "test", 3, 100)
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 1, "must not spend the whole budget once the goal holds")
        finally:
            path.unlink()

    def test_budget_is_bounded_and_reports_exhaustion(self):
        path = write_script(block("BASIL", 10))
        calls = []
        try:
            def useless(prompt, mode, script_path):
                calls.append(1)
                return ""

            with mock.patch.object(episode_topup, "_dispatch", useless), \
                 mock.patch.object(episode_topup, "_unused_sources", return_value=([], [], 0)), \
                 mock.patch.object(episode_topup, "_write_pass_sources", empty_sources):
                rc = episode_topup.top_up(path, "external", "test", 2, 6000)
            self.assertEqual(rc, 1)
            self.assertEqual(len(calls), 2, "must stop at max_attempts, not loop forever")
        finally:
            path.unlink()

    def test_already_long_enough_script_spends_nothing(self):
        """The normal case must be a no-op: no dispatch, no cost, no risk."""
        path = write_script(block("BASIL", 7000))
        try:
            with mock.patch.object(episode_topup, "_dispatch") as dispatch:
                rc = episode_topup.top_up(path, "external", "test", 2, 6000)
            self.assertEqual(rc, 0)
            dispatch.assert_not_called()
        finally:
            path.unlink()


class TestInsertionPoint:
    """A top-up must not leave the show trailing off into a repair.

    Borrowed from the manual rescue tool on main (topup_writer.py), which shipped the
    10-01 recovery: new segments go in BEFORE the episode's final block so the outro
    still closes the show. Appending after it was the flaw in the first cut of this file.
    """

    SIGNOFF = "[BASIL] That's the Killen Time Update. See you tomorrow."

    def _script(self, tmp_path):
        p = tmp_path / "ep.txt"
        p.write_text("\n".join([block("BASIL", 300), "[TRANSITION]",
                                block("BROOKE", 300), "[TRANSITION]", self.SIGNOFF]))
        return p

    def test_signoff_stays_last(self, tmp_path):
        p = self._script(tmp_path)
        added = episode_topup.insert_expansion(p, block("BASIL", 600))
        text = p.read_text()
        assert added == 600
        assert text.rstrip().endswith(self.SIGNOFF)
        assert text.index(block("BASIL", 600)) < text.index(self.SIGNOFF)

    def test_padding_sized_reply_is_discarded(self, tmp_path):
        """A stub is not material — accepting it would burn the budget on padding."""
        p = self._script(tmp_path)
        before = p.read_text()
        assert episode_topup.insert_expansion(p, block("BASIL", 5)) == 0
        assert p.read_text() == before

    def test_words_added_are_counted_the_voice_py_way(self, tmp_path):
        p = self._script(tmp_path)
        before_words = episode_topup.speech_words(p)
        added = episode_topup.insert_expansion(p, "[TRANSITION]\n" + block("BROOKE", 777))
        assert added == 777          # the [TRANSITION] tag is not a word
        # The delta between the two voice.py counts is exactly what we claim to have added
        # — a `wc -w` delta would be 2 higher (the speaker tags) and would overstate the
        # gain, which is the whole reason this loop measures the way it does.
        assert episode_topup.speech_words(p) - before_words == added


if __name__ == "__main__":
    unittest.main()