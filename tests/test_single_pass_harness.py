"""The New Hire single-pass harness's scanners, locked to their calibration.

`bin/test-single-pass.py --stage scan` feeds a PASS/FAIL criterion ("B has 0
seam defects"), so a scanner that fires on ordinary English makes that number
meaningless. These are the known-positive and known-negative cases measured
against the aired 09-25…09-28 episodes, so a future pattern edit cannot quietly
turn the criterion into noise.
"""
import importlib.util
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent / "bin" / "test-single-pass.py"
_spec = importlib.util.spec_from_file_location("test_single_pass_harness", _HARNESS)
tsp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsp)


def hits(text):
    import re
    out = []
    for name, pat in tsp.SEAM_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            out.append((name, m.group(0)))
    return out


class TestSeamPatterns(unittest.TestCase):
    def test_real_seams_are_caught(self):
        """Both real two-pass seams from the aired scripts, verbatim."""
        self.assertIn(("half_reference", "this half"),
                      hits("The thread worth carrying out of this half: Curry."))
        self.assertIn(("half_reference", "In the second half"),
                      hits("Here's the shape of the show. In the second half: Kalshi."))

    def test_ordinary_english_is_not_a_seam(self):
        """09-26 L166 and 09-27 L45 — prose about a film and about a case."""
        self.assertEqual([], hits("The first half of the review is the origin story."))
        self.assertEqual([], hits("supply the other half of Naam's case: an apple metaphor"))

    def test_public_show_name_is_not_a_leak(self):
        """'the Killen Time Update' is the show and is public by design."""
        self.assertEqual([], hits("This is the Killen Time Update for Monday."))

    def test_fleet_state_is_caught(self):
        for phrase in ("observer-system had forty-eight launch sites",
                       "the pr-review-sweeper handles it",
                       "it's logged in the build-pitches folder"):
            self.assertTrue(hits(phrase), phrase)

    def test_a_locked_on_podcast_is_not_a_task_status(self):
        self.assertEqual([], hits("a Brooklyn Nets preview with Locked On Nets."))


class TestBuildPitchDetector(unittest.TestCase):
    PITCH = (
        "[BASIL] Claude has an effort dial. Anthropic's docs say to sweep it per "
        "workload rather than leave everything on the default. On their own "
        "launch numbers, medium effort costs about seventy percent of high for "
        "roughly two and a half points less accuracy, and low costs about a "
        "third of the price. The ladder is run cheap first, then re-run only the "
        "failures harder. Matthew Berman's launch stream puts medium effort "
        "under a dollar a task and still outscoring max effort at over five. "
        "Artificial Analysis has the index scores behind it, and an arXiv paper "
        "makes the same argument from the other direction: judge agents on cost "
        "per successful task, because more effort sometimes only adds cost. "
        "The honest caveat is that those benchmarks are vendor-run and cover a "
        "different model on coding work, so this is a strong hypothesis rather "
        "than a proven saving. Still, if it holds it is a dial, not a system. "
        "[BROOKE] And it composes with everything else we already track. ")

    def test_needs_mechanism_source_and_airtime(self):
        ok, ev = tsp.detect_build_pitch(self.PITCH)
        self.assertTrue(ok)
        self.assertGreaterEqual(ev["words"], tsp.PITCH_MIN_WORDS)
        self.assertIn("anthropic", ev["sources"])

    def test_a_passing_clause_is_not_a_pitch(self):
        ok, _ = tsp.detect_build_pitch(
            "[BASIL] Anthropic shipped an effort dial, which is a medium-effort "
            "thing worth watching.")
        self.assertFalse(ok)

    def test_unsourced_mechanism_is_not_a_pitch(self):
        ok, _ = tsp.detect_build_pitch("[BASIL] " + self.PITCH
                                       .replace("Anthropic", "somebody")
                                       .replace("Artificial Analysis", "a blog")
                                       .replace("Matthew Berman", "a streamer")
                                       .replace("arXiv", "one"))
        self.assertFalse(ok)


class TestSpokenWords(unittest.TestCase):
    def test_speaker_tags_do_not_count_as_spoken(self):
        self.assertEqual(4, tsp.spoken_words("[BASIL] one two\n[BROOKE] three four"))


class TestSonnetOnePassPrompt(unittest.TestCase):
    """The Sonnet path must differ from pass 1 in ONE way only: it writes the
    whole episode. Anything else that drifts would make the rerun a different
    experiment than the one Kyle asked for — a fair fight on pass count alone."""

    def prompt(self, band):
        return tsp.sonnet_one_pass_prompt(band)

    def test_it_writes_the_whole_episode(self):
        for band in ("long", "short"):
            p = self.prompt(band).lower()
            self.assertIn("single pass", p)
            self.assertIn("whole episode", p)
            self.assertIn("write the outro yourself", p)

    def test_it_carries_no_two_pass_scaffolding(self):
        """Pass 1's own two-pass language must not survive into a one-pass prompt:
        it is the instruction that produced A's seams, and leaving it in would
        test a prompt that contradicts itself."""
        for band in ("long", "short"):
            p = self.prompt(band)
            for banned in ("FIRST HALF", "SECOND HALF", "first half",
                           "second half", "Another pass will write"):
                self.assertNotIn(banned, p,
                                 f"{band} prompt still contains {banned!r}")

    def test_it_covers_the_whole_show_not_just_pass_1s_beats(self):
        """A one-pass episode that skipped sports/entertainment/economics would
        be testing a different show, not a different pass count."""
        for band in ("long", "short"):
            p = self.prompt(band)
            for beat in ("SPORTS", "ENTERTAINMENT", "ECONOMICS", "OUTRO",
                         "QUICK HITS", "AI & TECH", "AGENTS & BUILDING"):
                self.assertIn(beat, p, f"{band} prompt is missing the {beat} beat")

    def test_it_keeps_the_discipline_pass_1_carries(self):
        """Evidence, dedup, the build-pitch rules and the no-private-system rule
        are what pass 1 had. Dropping them would hand B a laxer writer than A."""
        for band in ("long", "short"):
            p = self.prompt(band)
            for rule in (".tmp/topic-brief.txt", ".covered-*.json",
                         "build-pitches.md", "NO_VERIFIED_PITCH",
                         "BASIL/BROOKE/TRANSITION", "Do NOT render, mix, or publish"):
                self.assertIn(rule, p, f"{band} prompt dropped {rule!r}")

    def test_bands_carry_their_pre_registered_targets(self):
        self.assertIn("14,000-18,000", self.prompt("long"))
        self.assertIn("3,000-4,000", self.prompt("short"))

    def test_it_cannot_read_the_control(self):
        for band in ("long", "short"):
            self.assertIn("do not read or write anything under "
                          "scripts/killen-time-", self.prompt(band))


class TestLengthBands(unittest.TestCase):
    def test_the_long_band_is_the_spec_plus_fifteen_percent(self):
        lo = tsp.LONG_SPEC[0] * (1 - tsp.LONG_TOLERANCE)
        hi = tsp.LONG_SPEC[1] * (1 + tsp.LONG_TOLERANCE)
        self.assertEqual((11900.0, 20700.0), (lo, hi))


class TestJudgeLanes(unittest.TestCase):
    def test_two_judges_get_different_blind_orders(self):
        """A shared shuffle would let one judge's position preference leak into
        the other's read of the pair, so the seed is per-lane."""
        import hashlib
        import random
        orders = []
        for lane in ("space-bunny-free", "opus"):
            seed = int(hashlib.sha256(f"2026-09-28|{lane}".encode()).hexdigest()[:8], 16)
            o = ["A", "B"]
            random.Random(seed).shuffle(o)
            orders.append(tuple(o))
        self.assertEqual(len(set(orders)), 2, "both judges got the same order")

    def test_scores_parse_out_of_a_wrapped_reply(self):
        got, other, reason = tsp._parse_scores(
            'Sure!\n{"SOURCING": {"X": 4, "Y": 2}, "SUBSTANCE": {"X": 4, "Y": 2},'
            ' "PITCH": {"X": 3, "Y": 1}, "FLOW": {"X": 4, "Y": 3}, "REASON": "x"}')
        self.assertEqual((4, 4, 3, 4), tuple(got[k] for k in
                                            ("SOURCING", "SUBSTANCE", "PITCH", "FLOW")))
        self.assertEqual("x", reason)


if __name__ == "__main__":
    unittest.main()
