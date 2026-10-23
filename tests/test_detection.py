"""Detection tests. Run: python -m unittest discover -s tests -v  (no audio, no Qt needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from revelatetw.approval import ApprovalQueue  # noqa: E402
from revelatetw.detection import VerseDetector, normalise, words_to_digits  # noqa: E402
from revelatetw.store import VerseStore  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_kjv.json")


class DetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = VerseStore.from_json(SAMPLE)
        cls.det = VerseDetector(cls.store)

    def refs(self, text):
        return [(c.reference, c.match_type) for c in self.det.detect(text)]

    def test_numbers(self):
        self.assertEqual(words_to_digits("three sixteen"), "3 16")
        self.assertEqual(words_to_digits("twenty three"), "23")
        self.assertIn("1 corinthians 13 verse 4", normalise("first corinthians thirteen verse four"))

    def test_exact_digits(self):
        self.assertEqual(self.refs("Let's read John 3:16 together")[0], ("John 3:16", "exact"))

    def test_exact_spoken(self):
        self.assertEqual(self.refs("turn to john chapter three verse sixteen")[0][0], "John 3:16")

    def test_alias_and_space_form(self):
        self.assertEqual(self.refs("open Jn 3 16")[0][0], "John 3:16")

    def test_ordinal_book(self):
        self.assertEqual(self.refs("First Corinthians 13 verse 4 says charity suffereth long")[0][0],
                         "1 Corinthians 13:4")

    def test_missing_verse_not_in_pack(self):
        self.assertEqual(self.refs("Genesis 1:1"), [])

    def test_paraphrase_psalm23(self):
        r = self.det.detect("the Lord is my shepherd")
        self.assertEqual(r[0].reference, "Psalms 23:1")
        self.assertEqual(r[0].match_type, "paraphrase")
        self.assertGreaterEqual(r[0].confidence, 70)

    def test_no_scripture_no_candidates(self):
        self.assertEqual(self.det.detect("Let's talk about the parking situation and the budget."), [])


class QueueTests(unittest.TestCase):
    def test_dedupe_and_no_auto_projection(self):
        store = VerseStore.from_json(SAMPLE)
        det = VerseDetector(store)
        q = ApprovalQueue()
        added = q.add(det.detect("John 3:16"))
        self.assertEqual(len(added), 1)
        self.assertEqual(q.add(det.detect("John 3:16")), [])        # deduped within window
        self.assertIsNone(q.live)                                    # detection never projects
        q.approve(added[0].id)
        self.assertEqual(q.live.reference, "John 3:16")
        q.set_blank(True)
        self.assertEqual(q.state, "blank")


if __name__ == "__main__":
    unittest.main()
