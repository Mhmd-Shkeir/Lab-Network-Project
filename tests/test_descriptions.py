"""Offline checks of the description cleaning rules."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
import descriptions as d  # noqa: E402


class DescriptionTests(unittest.TestCase):
    def test_catalogue_only_text_becomes_empty(self):
        self.assertEqual(d.clean_description("128 p. : 21 cm Includes index"), "")
        self.assertEqual(d.clean_description(None), "")

    def test_leading_catalogue_text_is_removed_but_the_blurb_is_kept(self):
        self.assertTrue(d.clean_description("72 pages : 19 cm When Nancy's family has company, a ring disappears").startswith("When Nancy"))
        self.assertEqual(d.clean_description('"A Berkley book." Two friends must find a killer'), "Two friends must find a killer")

    def test_html_and_lists_are_flattened(self):
        self.assertEqual(d.raw_text(["<p>One</p>", "two &amp; three"]), "One two & three")

    def test_boilerplate_is_detected(self):
        self.assertTrue(d.is_boilerplate("Book digitized by Google from the library of Harvard University and uploaded to the Internet Archive by user tpb."))
        self.assertFalse(d.is_boilerplate("A girl runs away and finds fire lizards."))


if __name__ == "__main__":
    unittest.main()
