import unittest

from ab_proofread.core import Suggestion, corrected_text, parse_matches, utf16_to_codepoint


class CoreTests(unittest.TestCase):
    def test_utf16_offsets_and_surrogate_boundary(self):
        self.assertEqual(utf16_to_codepoint("A😀B", 3), 2)
        with self.assertRaises(ValueError):
            utf16_to_codepoint("A😀B", 2)

    def test_parse_emoji_and_safe_exclusions(self):
        text = "😀 teh https://example.com teh@example.com /tmp/teh `teh` #teh"
        payload = {"matches": [
            {"offset": 3, "length": 3, "message": "typo", "replacements": [{"value": "the"}], "rule": {"id": "T"}},
            {"offset": 27, "length": 3, "message": "typo", "replacements": [{"value": "the"}], "rule": {"id": "T"}},
        ]}
        got = parse_matches(text, payload)
        self.assertEqual([(s.start, s.end) for s in got], [(2, 5)])
        self.assertEqual(text[got[0].start:got[0].end], "teh")

    def test_explicit_choice_and_rejection(self):
        text = "teh"
        suggestions = [Suggestion(0, 3, "typo", ("the", "ten"), "T")]
        self.assertEqual(corrected_text(text, suggestions, {0: "the"}), "the")
        self.assertEqual(corrected_text(text, suggestions, {}), "teh")
        with self.assertRaises(ValueError):
            corrected_text(text, suggestions, {0: "bad"})
        with self.assertRaises(ValueError):
            corrected_text("abcdef", [Suggestion(0, 3, "", (), ""), Suggestion(2, 5, "", (), "")], {0:"x",1:"y"})

    def test_invalid_match_bounds(self):
        with self.assertRaises(ValueError):
            parse_matches("abc", {"matches": [{"offset": 1, "length": 9}]})


if __name__ == "__main__":
    unittest.main()
