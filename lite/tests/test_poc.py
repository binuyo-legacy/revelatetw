import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import poc


class T(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(poc.parse_reference("John 3:16"), (43, 3, 16))
        self.assertIsNone(poc.parse_reference("Nope 1:1"))

    def test_john_316_kjv(self):
        t = poc.get_verse("KJV", 43, 3, 16)
        self.assertTrue(t.startswith("For God so loved the world"))

    def test_missing(self):
        self.assertIsNone(poc.get_verse("KJV", 43, 3, 999))


if __name__ == "__main__":
    unittest.main()
