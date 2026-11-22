"""Offline cohort rules: optional blanks/zero views, missing authors, quality flags and invalid inputs."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'scrapers'))
from prepare_popularity_dataset import rejection_reasons


def complete_row():
    return dict(identifier='example', title='A book', creators='An Author', first_creator='An Author',
                publication_year='2000', subjects='Science fiction', language='eng',
                addeddate='2020-01-01T00:00:00Z', retrieved_at_utc='2026-11-22T16:00:00Z',
                scanned_page_count='250', views_all_time='0', openlibrary_work='OL1W', ol_group='OL1W',
                description=' '.join(['word']*25), description_ready='1', author_missing='0',
                status='ok', error='', openlibrary_edition='')


class PopularityCohortTests(unittest.TestCase):
    def test_zero_views_and_optional_blank_fields_are_valid(self):
        self.assertEqual(rejection_reasons(complete_row()), [])

    def test_missing_author_is_rejected_even_with_successful_collection(self):
        row=complete_row(); row.update(creators='None', first_creator='', author_missing='1')
        reasons=rejection_reasons(row)
        self.assertIn('missing:creators', reasons)
        self.assertIn('missing:first_creator', reasons)
        self.assertIn('author_flagged_missing', reasons)

    def test_long_text_does_not_override_failed_description_quality_flag(self):
        row=complete_row(); row['description_ready']='0'
        self.assertIn('description_not_ready', rejection_reasons(row))

    def test_invalid_numeric_or_date_values_are_rejected(self):
        for field,value in [('views_all_time','nan'), ('views_all_time','inf'), ('views_all_time','-1'),
                            ('scanned_page_count','0'), ('publication_year','unknown'),
                            ('addeddate','not-a-date')]:
            with self.subTest(field=field, value=value):
                row=complete_row();row[field]=value
                prefix = 'missing:' if value == 'nan' else 'invalid:'
                self.assertIn(prefix+field, rejection_reasons(row))
        row=complete_row(); row['addeddate']='2030-01-01T00:00:00Z'
        self.assertIn('negative_archive_age', rejection_reasons(row))


if __name__ == '__main__':
    unittest.main()
