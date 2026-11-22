"""Analysis-environment tests for hand-entered book inputs (no model fitting)."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manual_book_prediction import prepare_book

DEFAULTS={'publication_year':2000, 'pages':300, 'archive_years':7.0, 'n_creators':1, 'n_subjects':5}


class ManualInputTests(unittest.TestCase):
    def test_title_and_description_work_with_visible_metadata_defaults(self):
        frame, assumptions=prepare_book(title='My book', description='A story about a family.', defaults=DEFAULTS)
        self.assertEqual(frame.publication_year.iloc[0],2000)
        self.assertEqual(frame.age_years.iloc[0],7.0)
        self.assertTrue({'publication_year','pages','archive_years','author','subjects'} <= set(assumptions['input']))

    def test_explicit_values_and_zero_archive_age_are_preserved(self):
        frame,assumptions=prepare_book(title='A book',description=' '.join(['story']*30), author='Writer, A | Writer, B',
            publication_year=2020,pages=120,archive_years=0,subjects=['Fantasy','Juvenile fiction'],defaults=DEFAULTS)
        self.assertEqual(frame.n_creators.iloc[0],2)
        self.assertEqual(frame.n_subjects.iloc[0],2)
        self.assertEqual(frame.genre_fantasy.iloc[0],1)
        self.assertEqual(frame.juvenile.iloc[0],1)
        self.assertEqual(frame.age_years.iloc[0],0)
        self.assertTrue(assumptions.empty)

    def test_genre_is_turned_into_a_subject_without_duplicate_tags(self):
        frame,_=prepare_book(title='Book',genre='fantasy',subjects=['Fantasy'],defaults=DEFAULTS)
        self.assertEqual(frame.n_subjects.iloc[0],1)
        self.assertEqual(frame.genre_fantasy.iloc[0],1)

    def test_invalid_inputs_fail_clearly(self):
        for extra in [{'pages':0},{'archive_years':-1},{'publication_year':'unknown'},{'genre':'invalid'},{'juvenile':'false'}]:
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                prepare_book(title='Book',defaults=DEFAULTS,**extra)
        with self.assertRaises(ValueError):prepare_book(title='',defaults=DEFAULTS)


if __name__=='__main__':unittest.main()
