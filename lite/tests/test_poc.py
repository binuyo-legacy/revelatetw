import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import poc


class T(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(poc.parse_reference("John 3:16"), (43, 3, 16, 16))
        self.assertIsNone(poc.parse_reference("Nope 1:1"))

    def test_abbreviations(self):
        self.assertEqual(poc.parse_reference("Rom 8:28"), (45, 8, 28, 28))
        self.assertEqual(poc.parse_reference("1 cor 13:4"), (46, 13, 4, 4))
        self.assertEqual(poc.parse_reference("1cor 13:4"), (46, 13, 4, 4))
        self.assertEqual(poc.parse_reference("Ps 23:1-3"), (19, 23, 1, 3))
        self.assertEqual(poc.parse_reference("psalm 23 1"), (19, 23, 1, 1))
        self.assertEqual(poc.parse_reference("Gen. 1:1"), (1, 1, 1, 1))
        self.assertEqual(poc.parse_reference("Revelation 22:21"), (66, 22, 21, 21))
        self.assertIsNone(poc.parse_reference("John 3:18-16"))

    def test_many_passages_all_translations(self):
        for tr in poc.list_translations():
            for r in ["Genesis 1:1", "Ps 23:1", "Rom 8:28", "1 cor 13:4", "Rev 22:21", "Matt 5:3"]:
                p = poc.parse_reference(r)
                self.assertTrue(poc.get_passage(tr, *p), (tr, r))
            self.assertIn(" 17 ", poc.get_passage(tr, 43, 3, 16, 17))

    def test_known_text(self):
        self.assertIn("Lord is my shepherd", poc.get_passage("KJV", 19, 23, 1, 1))
        self.assertIn("Charity suffereth long", poc.get_passage("KJV", 46, 13, 4, 4))

    def test_john_316_kjv(self):
        t = poc.get_verse("KJV", 43, 3, 16)
        self.assertTrue(t.startswith("For God so loved the world"))

    def test_missing(self):
        self.assertIsNone(poc.get_verse("KJV", 43, 3, 999))


if __name__ == "__main__":
    unittest.main()
