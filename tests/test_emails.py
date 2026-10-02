import unittest
from datetime import date, datetime
from draws import DRAWS, UK, DrawResult
from emails import errorEmail, formatPostcode, weeklyEmail, winEmail
from emailTemplate import Grid, Note, render
from history import History
import previewEmails

DRAW = {d.key: d for d in DRAWS}
NOW = datetime(2026, 10, 1, 18, 1, tzinfo=UK)


class EmailTest(unittest.TestCase):
    def test_every_email_renders_without_dashes(self):
        for name, email in previewEmails.samples():
            with self.subTest(name):
                page = render(email)
                self.assertIn(email.preheader.split('.')[0], page)
                self.assertNotIn('—', page)
                self.assertNotIn('–', page)

    def test_formats_a_compact_postcode(self):
        self.assertEqual(formatPostcode('zz99zz'), 'ZZ9 9ZZ')
        self.assertEqual(formatPostcode('SW1A 1AA'), 'SW1A 1AA')

    def test_win_links_to_the_claim_page_and_warns_only_about_first_come_draws(self):
        wins = [DrawResult(DRAW['miniDraw'], NOW.date(), 'ZZ9 9ZZ', True),
                DrawResult(DRAW['mainDraw'], NOW.date(), 'ZZ9 9ZZ', True)]
        email = winEmail(wins, 'ZZ99ZZ', NOW)
        self.assertEqual(email.cta, ('Claim your prize', 'https://pickmypostcode.com/'))
        [note] = [b for b in email.blocks if isinstance(b, Note)]
        self.assertIn('The Mini Draw is first come', note.text)
        self.assertNotIn('Main Draw', note.text)
        self.assertIn('href="https://pickmypostcode.com/"', render(email))

    def test_main_draw_win_has_no_first_come_warning(self):
        email = winEmail([DrawResult(DRAW['mainDraw'], NOW.date(), 'ZZ9 9ZZ', True)], 'ZZ99ZZ', NOW)
        self.assertFalse(any(isinstance(b, Note) for b in email.blocks))

    def test_weekly_grid_marks_wins_misses_and_unchecked_draws(self):
        sunday = date(2026, 10, 4)
        history = History('unused', {}, 'ZZ99ZZ')
        history.record(DrawResult(DRAW['mainDraw'], date(2026, 9, 28), 'ZZ9 9ZZ', True))
        history.record(DrawResult(DRAW['mainDraw'], date(2026, 9, 29), 'AA1 1AA', False))
        [grid] = [b for b in weeklyEmail(history, sunday, 'Verdict.').blocks if isinstance(b, Grid)]
        self.assertEqual(grid.days[0], ('Mon', '28'))
        self.assertEqual(dict(grid.rows)['Main Draw'], ['win', 'ok', 'none', 'none', 'none', 'none', 'none'])

    def test_escapes_error_text(self):
        page = render(errorEmail(['Checking the draws failed:\n<script>alert(1)</script>'], NOW))
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)


if __name__ == '__main__':
    unittest.main()
