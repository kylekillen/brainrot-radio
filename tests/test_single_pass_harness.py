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


if __name__ == "__main__":
    unittest.main()
