import unittest
from datetime import date, datetime, timezone
from unittest import mock

import requests

import draws
from draws import fetchDraws, readDraws
from tests.support import POSTCODE, drawResults, uk

THURSDAY_2PM = uk(2026, 10, 1, 14, 0)


def read(now=THURSDAY_2PM, **overrides):
    results, missing = readDraws(drawResults(**overrides), POSTCODE, now)
    return {r.draw.key: r for r in results}, [(d.key, day) for d, day in missing]


class MiddayDrawTest(unittest.TestCase):
    def test_win_is_claimable_from_noon_until_the_next_noon(self):
        results, missing = read(main='zz99zz')  # matching ignores case and spacing
        main = results['mainDraw']
        self.assertEqual(missing, [])
        self.assertEqual(main.day, date(2026, 10, 1))
        self.assertTrue(main.hasWon)
        self.assertFalse(main.canClaim(uk(2026, 10, 1, 11, 59)))
        self.assertTrue(main.canClaim(uk(2026, 10, 2, 11, 59)))
        self.assertFalse(main.canClaim(uk(2026, 10, 2, 12, 0)))
        self.assertFalse(results['surveyDraw'].hasWon)

    def test_requires_a_postcode(self):
        with self.assertRaises(ValueError):
            readDraws(drawResults(), ' ', THURSDAY_2PM)


class MiniDrawTest(unittest.TestCase):
    def tonight(self, now=uk(2026, 10, 1, 18, 1), **overrides):
        return read(now, mini=POSTCODE, miniAt='2026-10-01 18:00:00', **overrides)

    def test_open_from_6pm_until_just_before_2am(self):
        mini = self.tonight()[0]['miniDraw']
        self.assertEqual(mini.day, date(2026, 10, 1))
        self.assertFalse(mini.canClaim(uk(2026, 10, 1, 17, 59)))
        self.assertTrue(mini.canClaim(uk(2026, 10, 1, 18, 0)))
        self.assertTrue(mini.canClaim(uk(2026, 10, 2, 1, 59, 59)))
        self.assertFalse(mini.canClaim(uk(2026, 10, 2, 2, 0)))

    def test_future_dated_result_is_unavailable_not_a_win(self):
        results, missing = self.tonight(now=uk(2026, 10, 1, 17, 59))
        self.assertNotIn('miniDraw', results)
        self.assertEqual(missing, [('miniDraw', date(2026, 9, 30))])

    def test_result_still_shown_before_6pm_is_the_previous_evenings_closed_draw(self):
        results, missing = read(mini=POSTCODE, miniAt='2026-09-30 18:00:00')
        mini = results['miniDraw']
        self.assertEqual(missing, [])  # expected at 2pm, not stale
        self.assertEqual(mini.day, date(2026, 9, 30))
        self.assertTrue(mini.hasWon)
        self.assertFalse(mini.canClaim(THURSDAY_2PM))

    def test_claimed_by_claim_count_or_inactive_status(self):
        for overrides in ({'miniClaims': 1}, {'miniStatus': 'claimed'}):
            mini = self.tonight(**overrides)[0]['miniDraw']
            self.assertTrue(mini.hasWon)
            self.assertTrue(mini.claimed)
            self.assertFalse(mini.canClaim(uk(2026, 10, 1, 18, 1)))

    def test_missing_claim_status_is_unavailable_not_claimable(self):
        for field in ('status', 'claims', 'max_claims'):
            payload = drawResults(mini=POSTCODE, miniAt='2026-10-01 18:00:00')
            del payload['mini'][field]
            results, missing = readDraws(payload, POSTCODE, uk(2026, 10, 1, 18, 1))
            self.assertNotIn('miniDraw', [r.draw.key for r in results])
            self.assertEqual([d.key for d, _ in missing], ['miniDraw'])

    def test_closes_at_2am_across_the_october_clock_change(self):
        # Sat 24 Oct 2026 18:00 BST; clocks go back at 02:00 BST, so 01:00-02:00 happens twice.
        mini = read(uk(2026, 10, 24, 18, 1), mini=POSTCODE, miniAt='2026-10-24 18:00:00')[0]['miniDraw']
        self.assertFalse(mini.canClaim(datetime(2026, 10, 24, 16, 59, tzinfo=timezone.utc)))
        self.assertTrue(mini.canClaim(datetime(2026, 10, 24, 17, 0, tzinfo=timezone.utc)))
        self.assertTrue(mini.canClaim(datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)))  # second 01:30, GMT
        self.assertFalse(mini.canClaim(datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc)))  # 02:00 GMT

    def test_closes_at_2am_across_the_march_clock_change(self):
        # Sat 28 Mar 2026 18:00 GMT; 02:00 BST on Sunday is 01:00 UTC.
        mini = read(uk(2026, 3, 28, 18, 1), mini=POSTCODE, miniAt='2026-03-28 18:00:00')[0]['miniDraw']
        self.assertTrue(mini.canClaim(datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc)))
        self.assertFalse(mini.canClaim(datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)))


class StackpotTest(unittest.TestCase):
    def test_morning_and_evening_draws_are_separate(self):
        morning = read(stackpot=('SA1 1AA', POSTCODE), stackpotAt='2026-10-01 09:00:00')[0]
        evening = read(uk(2026, 10, 1, 21, 1), stackpot=(POSTCODE,), stackpotAt='2026-10-01 21:00:00')[0]
        self.assertIn('stackpotDraw', morning)
        self.assertNotIn('stackpotEveningDraw', morning)
        self.assertTrue(morning['stackpotDraw'].canClaim(uk(2026, 10, 1, 20, 59)))
        self.assertFalse(morning['stackpotDraw'].canClaim(uk(2026, 10, 1, 21, 0)))
        night = evening['stackpotEveningDraw']
        self.assertEqual(night.day, date(2026, 10, 1))
        self.assertTrue(night.canClaim(uk(2026, 10, 2, 0, 30)))  # after midnight, still last night's draw
        self.assertFalse(night.canClaim(uk(2026, 10, 2, 9, 0)))

    def test_postcode_in_claimed_list_is_a_claimed_win(self):
        stackpot = read(stackpot=('SA1 1AA',), stackpotClaimed=(POSTCODE,))[0]['stackpotDraw']
        self.assertTrue(stackpot.hasWon)
        self.assertTrue(stackpot.claimed)
        self.assertFalse(stackpot.canClaim(THURSDAY_2PM))

    def test_empty_list_is_a_readable_no_win(self):
        results, missing = read(stackpot=())
        self.assertEqual(missing, [])
        self.assertFalse(results['stackpotDraw'].hasWon)


class UnavailableDrawTest(unittest.TestCase):
    def test_missing_or_malformed_draws_are_unavailable_not_losing(self):
        payload = drawResults()
        del payload['mini']
        payload['main']['result'] = ''
        payload['survey']['dateandtime'] = 'yesterday'
        payload['video']['dateandtime'] = '2026-10-01 13:30:00'  # not a scheduled draw time
        payload['stackpot']['result'] = ['SA1 1AA', None]
        payload['bonus'] = []
        results, missing = readDraws(payload, POSTCODE, THURSDAY_2PM)
        self.assertEqual(results, [])
        self.assertEqual([d.label for d, _ in missing], ['Main Draw', 'Survey Draw', 'Video Draw', 'Stackpot 9am',
                                                        'Bonus £5', 'Bonus £10', 'Bonus £20', 'Mini Draw'])

    def test_stale_results_are_kept_as_history_but_every_latest_draw_is_missing(self):
        results, missing = read(uk(2026, 10, 3, 14, 0))  # payload is from Thursday; it's now Saturday
        self.assertEqual(len(results), 8)
        self.assertEqual(missing, [('mainDraw', date(2026, 10, 3)), ('surveyDraw', date(2026, 10, 3)),
                                   ('videoDraw', date(2026, 10, 3)), ('stackpotDraw', date(2026, 10, 3)),
                                   ('bonusDrawFive', date(2026, 10, 3)), ('bonusDrawTen', date(2026, 10, 3)),
                                   ('bonusDrawTwenty', date(2026, 10, 3)), ('miniDraw', date(2026, 10, 2))])


class FetchTest(unittest.TestCase):
    def response(self, body):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = body
        return response

    def test_retries_briefly_then_returns_draw_results(self):
        good = self.response({'data': {'drawResults': drawResults()}})
        sleeps = []
        with mock.patch.object(draws.requests, 'get', side_effect=[requests.ConnectionError('down'),
                                                                    self.response({'error': 'busy'}), good]):
            self.assertEqual(fetchDraws(sleep=sleeps.append), drawResults())
        self.assertEqual(sleeps, [10, 20])

    def test_gives_up_after_three_attempts(self):
        with mock.patch.object(draws.requests, 'get', side_effect=requests.Timeout('slow')) as get:
            with self.assertRaises(requests.Timeout):
                fetchDraws(sleep=lambda _: None)
        self.assertEqual(get.call_count, 3)


if __name__ == '__main__':
    unittest.main()
