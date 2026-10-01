import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest import mock

import run
import scheduler
from draws import DRAWS, DrawResult
from history import History, openHistory
from summariseWeeklyResults import summariseWeeklyResults
from tests.support import POSTCODE, FakeClock, drawResults, latestResults, uk

WIN = 'You have won the postcode lottery 🎉'
WEEKLY = 'Weekly postcode lottery data summary 📊'
ERROR = 'Script Error Notification 🚨'
OTHER_POSTCODE = 'YY8 8YY'
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Stop(BaseException):
    pass


class CheckerTest(unittest.TestCase):
    """Runs run.main() against a fake API, browser and mailbox, with a temporary logs directory."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.logs = os.path.join(tmp.name, 'logs')
        self.emails = []
        self.deliver = True
        self.payloads = []
        self.fetches = 0
        self.browser = mock.Mock()
        for patcher in (
            mock.patch.object(run, 'LOGS_DIR', self.logs),
            mock.patch.object(run, 'sendEmail', side_effect=self._send),
            mock.patch.object(run, 'fetchDraws', side_effect=self._fetch),
            mock.patch.object(run, 'browserLogin', self.browser),
            mock.patch.dict(os.environ, {'YOUR_POSTCODE': POSTCODE, 'NOTIFICATION_EMAIL_ADDRESS': 'me@example.com'}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _send(self, to, subject, message, html_message, attachment_path=None):
        self.emails.append({'subject': subject, 'text': message, 'html': html_message})
        return self.deliver(subject) if callable(self.deliver) else self.deliver

    def _fetch(self, sleep=None):
        self.fetches += 1
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        if isinstance(payload, Exception):
            raise payload
        return payload

    def check(self, when, *payloads, scheduled=True, retry=False):
        """One check at `when`; without payloads, the API shows exactly what it should then."""
        self.payloads = list(payloads) or [latestResults(when)]
        self.fetches = 0
        self.emails.clear()
        self.clock = clock = FakeClock(when)
        with redirect_stdout(io.StringIO()):
            self.retrySoon = run.main(scheduled=scheduled, retry=retry, now=clock.now, sleep=clock.sleep)
        return clock

    def sent(self, subject):
        return [e for e in self.emails if e['subject'] == subject]

    def state(self, name='pastData.json'):
        with open(os.path.join(self.logs, name)) as f:
            return json.load(f)

    def entry(self, day, key):
        return self.state()['draws'].get(day, {}).get(key)

    def setAside(self, prefix):
        return [name for name in os.listdir(self.logs) if name.startswith(prefix)]


class WinAlertTest(CheckerTest):
    def test_active_mini_win_is_emailed_once_across_checks(self):
        evening, night = uk(2026, 10, 1, 18, 1), uk(2026, 10, 1, 21, 1)
        self.check(evening, latestResults(evening, mini=POSTCODE))
        self.assertEqual(len(self.sent(WIN)), 1)
        self.assertIn('Mini Draw', self.sent(WIN)[0]['text'])
        self.assertIn('claim before Fri 02 Oct 02:00', self.sent(WIN)[0]['text'])
        self.assertFalse(self.retrySoon)

        self.check(night, latestResults(night, mini=POSTCODE))  # a later check, or a restarted container
        self.check(uk(2026, 10, 2, 0, 30), latestResults(night, mini=POSTCODE), scheduled=False)
        self.assertEqual(self.sent(WIN), [])
        self.assertEqual(self.sent(ERROR), [])
        self.assertTrue(self.entry('2026-10-01', 'miniDraw')['notified'])

    def test_waits_for_a_just_due_mini_then_alerts(self):
        evening = uk(2026, 10, 1, 18, 1)
        stale = latestResults(evening, miniAt='2026-09-30 18:00:00')
        clock = self.check(evening, stale, latestResults(evening, mini=POSTCODE))
        self.assertEqual(self.fetches, 2)
        self.assertEqual(clock.slept, run.REFETCH_SECONDS)
        self.assertEqual(len(self.sent(WIN)), 1)
        self.assertEqual(self.sent(ERROR), [])

    def test_unpublished_draw_is_reported_unavailable_after_waiting_and_retried(self):
        evening = uk(2026, 10, 1, 18, 1)
        clock = self.check(evening, latestResults(evening, miniAt='2026-09-30 18:00:00'))
        self.assertLessEqual(clock.current, uk(2026, 10, 1, 18, 15))
        self.assertLessEqual(self.fetches, 15)
        self.assertIsNone(self.entry('2026-10-01', 'miniDraw'))
        [error] = self.sent(ERROR)
        self.assertIn('Unavailable from the results API: Mini Draw (Thu 01 Oct 18:00)', error['text'])
        self.assertTrue(self.retrySoon)  # still open until 2am

    def test_closed_or_claimed_mini_wins_are_recorded_but_not_emailed(self):
        afternoon, evening = uk(2026, 10, 1, 14, 0), uk(2026, 10, 1, 18, 1)
        self.check(afternoon, latestResults(afternoon, mini=POSTCODE))
        self.check(evening, latestResults(evening, mini=POSTCODE, miniClaims=1))
        self.assertEqual(self.sent(WIN), [])
        self.assertTrue(self.entry('2026-09-30', 'miniDraw')['hasWon'])
        self.assertTrue(self.entry('2026-10-01', 'miniDraw')['claimed'])

    def test_morning_and_evening_stackpots_each_alert_once(self):
        morning, night = uk(2026, 10, 1, 9, 1), uk(2026, 10, 1, 21, 1)
        self.check(morning, latestResults(morning, stackpot=('SA1 1AA', POSTCODE)))
        self.assertIn('Stackpot 9am', self.sent(WIN)[0]['text'])
        self.check(morning + timedelta(hours=5), latestResults(morning, stackpot=('SA1 1AA', POSTCODE)))
        self.assertEqual(self.sent(WIN), [])

        self.check(night, latestResults(night, stackpot=('NEW 1AA', POSTCODE)))
        [win] = self.sent(WIN)
        self.assertIn('Stackpot 9pm', win['text'])
        self.assertNotIn('Stackpot 9am', win['text'])
        self.check(night + timedelta(minutes=30), latestResults(night, stackpot=('NEW 1AA', POSTCODE)))
        self.assertEqual(self.sent(WIN), [])
        self.assertTrue(self.entry('2026-10-01', 'stackpotDraw')['hasWon'])

    def test_failed_win_email_is_retried_until_delivered_then_not_repeated(self):
        evening, night = uk(2026, 10, 1, 18, 1), uk(2026, 10, 1, 21, 1)
        self.deliver = False
        clock = self.check(evening, latestResults(evening, mini=POSTCODE))
        self.assertEqual(len(self.sent(WIN)), run.EMAIL_ATTEMPTS)
        self.assertGreaterEqual(clock.slept, run.EMAIL_RETRY_SECONDS)
        self.assertIsNone(self.entry('2026-10-01', 'miniDraw')['notified'])
        self.assertTrue(self.retrySoon)

        self.deliver = True
        self.check(night, latestResults(night, mini=POSTCODE))
        self.assertEqual(len(self.sent(WIN)), 1)
        self.check(uk(2026, 10, 1, 23, 0), latestResults(night, mini=POSTCODE), scheduled=False)
        self.assertEqual(self.sent(WIN), [])
        self.assertFalse(self.retrySoon)

    def test_retry_never_sends_a_win_after_it_closes(self):
        evening, late = uk(2026, 10, 1, 18, 1), uk(2026, 10, 2, 1, 59, 40)
        self.deliver = lambda subject: subject != WIN
        self.check(evening, latestResults(evening, mini=POSTCODE))
        self.check(late, latestResults(late, mini=POSTCODE), retry=True)
        self.assertEqual(len(self.sent(WIN)), 1)  # 01:59:40 failed; at 02:00:10 the prize had closed
        self.assertFalse(self.retrySoon)
        self.check(uk(2026, 10, 2, 9, 1))
        self.assertEqual(self.sent(WIN), [])

    def test_api_failure_still_retries_earlier_wins_and_reports_the_error(self):
        afternoon = uk(2026, 10, 1, 14, 0)
        self.deliver = lambda subject: subject != WIN
        self.check(afternoon, latestResults(afternoon, main=POSTCODE))
        self.deliver = True
        self.check(uk(2026, 10, 1, 18, 1), ConnectionError('API down'))
        self.assertEqual(len(self.sent(WIN)), 1)
        self.assertEqual(len(self.sent(ERROR)), 1)
        self.assertIn('API down', self.sent(ERROR)[0]['text'])
        self.assertTrue(self.entry('2026-10-01', 'mainDraw')['notified'])
        self.assertTrue(self.retrySoon)


class SchedulerRetryTest(CheckerTest):
    def test_short_email_outage_at_9pm_is_recovered_well_before_2am_without_duplicates(self):
        night = uk(2026, 10, 1, 21, 1)
        self.payloads = [latestResults(night, mini=POSTCODE)]
        failures = iter([False] * run.EMAIL_ATTEMPTS)
        self.deliver = lambda subject: next(failures, True) if subject == WIN else True
        clock = FakeClock(night)
        calls = []

        def check(retry):
            calls.append((clock.now(), retry))
            if len(calls) == 3:
                raise Stop
            return run.main(scheduled=True, retry=retry, now=clock.now, sleep=clock.sleep)

        with redirect_stdout(io.StringIO()), self.assertRaises(Stop):
            scheduler.runForever(check, now=clock.now, sleep=clock.sleep)

        (first, firstRetry), (second, secondRetry), (third, thirdRetry) = calls
        self.assertEqual((first, firstRetry), (night, False))
        self.assertTrue(secondRetry)
        self.assertLess(second, uk(2026, 10, 1, 21, 10))
        self.assertEqual((third, thirdRetry), (uk(2026, 10, 2, 9, 1), False))  # back to the normal schedule
        self.assertEqual(len(self.sent(WIN)), run.EMAIL_ATTEMPTS + 1)  # three failures, one delivery
        self.assertEqual(self.entry('2026-10-01', 'miniDraw')['notified'], second.isoformat())
        self.assertEqual(self.browser.call_count, 1)  # retries don't sign in again


class BrowserTest(CheckerTest):
    def test_sign_in_runs_once_a_day_from_2pm_on_scheduled_checks(self):
        self.check(uk(2026, 10, 1, 9, 1))
        self.browser.assert_not_called()
        self.check(uk(2026, 10, 1, 14, 0))
        self.check(uk(2026, 10, 1, 18, 1))
        self.assertEqual(self.browser.call_count, 1)
        self.assertEqual(self.state()['lastBrowserLogin'], '2026-10-01')
        self.check(uk(2026, 10, 2, 10, 0), scheduled=False)  # a manual run always signs in
        self.assertEqual(self.browser.call_count, 2)
        self.assertEqual(self.sent(ERROR), [])

    def test_sign_in_failure_does_not_block_alerts_and_emails_one_error_a_day(self):
        afternoon = uk(2026, 10, 1, 14, 0)
        self.browser.side_effect = RuntimeError('sign-in button missing')
        self.check(afternoon, latestResults(afternoon, main=POSTCODE))
        self.assertEqual(len(self.sent(WIN)), 1)
        self.assertEqual(len(self.sent(ERROR)), 1)
        self.assertIn('sign-in button missing', self.sent(ERROR)[0]['text'])
        self.assertIsNone(self.state()['lastBrowserLogin'])

        self.check(uk(2026, 10, 1, 18, 1))  # retried later the same day, without another error email
        self.assertEqual(self.browser.call_count, 2)
        self.assertEqual(self.sent(ERROR), [])
        self.check(uk(2026, 10, 2, 14, 0))
        self.assertEqual(len(self.sent(ERROR)), 1)

    def test_unreadable_draw_is_reported(self):
        morning = uk(2026, 10, 1, 9, 1)
        payload = latestResults(morning)
        del payload['mini']
        self.check(morning, payload)
        self.assertIn('Unavailable from the results API: Mini Draw (Wed 30 Sep 18:00)', self.sent(ERROR)[0]['text'])


class WeeklySummaryTest(CheckerTest):
    def test_sent_once_after_the_final_sunday_check(self):
        afternoon, night = uk(2026, 10, 4, 14, 0), uk(2026, 10, 4, 21, 1)
        self.check(afternoon, latestResults(afternoon, main=POSTCODE))
        self.assertEqual(self.sent(WEEKLY), [])

        self.check(night, latestResults(night, main=POSTCODE, stackpot=('SE1 1AA',)))
        [weekly] = self.sent(WEEKLY)
        text = weekly['text']
        self.assertIn('You had a win this week', text)
        self.assertIn("draws weren't checked, so this week's results are incomplete", text)
        self.assertIn('Sunday, 2026-10-04', text)
        self.assertIn('Main Draw: Yes (ZZ9 9ZZ)', text)
        self.assertIn('Stackpot 9am: No (SA1 1AA, SB1 1BB)', text)
        self.assertIn('Stackpot 9pm: No (SE1 1AA)', text)
        self.assertIn('Mini Draw: No (MI1 1AA)', text)
        self.assertIn('Monday, 2026-09-28', text)
        self.assertIn('Main Draw: Not checked', text)
        self.assertNotIn('2026-09-27', text)

        self.check(uk(2026, 10, 4, 22, 0), scheduled=False)
        self.check(uk(2026, 10, 5, 9, 1))
        self.assertEqual(self.sent(WEEKLY), [])

    def test_waits_for_results_fetched_after_9pm_not_a_check_that_merely_ends_after_it(self):
        self.browser.side_effect = lambda: self.clock.sleep(240)
        self.check(uk(2026, 10, 4, 20, 59))  # results fetched at 20:59; the sign-in finishes at 21:03
        self.assertEqual(self.clock.now(), uk(2026, 10, 4, 21, 3))
        self.assertEqual(self.sent(WEEKLY), [])
        self.assertIsNone(self.state()['lastWeeklySummary'])

        night = uk(2026, 10, 4, 21, 3)  # the scheduler's catch-up check
        self.check(night, latestResults(night, stackpot=('SE1 1AA',)))
        [weekly] = self.sent(WEEKLY)
        self.assertIn('Stackpot 9pm: No (SE1 1AA)', weekly['text'])
        self.assertIn('Sunday, 2026-10-04', weekly['text'])
        self.assertEqual(self.browser.call_count, 1)

    def test_failed_summary_is_retried_at_the_next_check(self):
        self.deliver = lambda subject: subject != WEEKLY
        self.check(uk(2026, 10, 4, 21, 1))
        self.assertIsNone(self.state()['lastWeeklySummary'])
        self.deliver = True
        self.check(uk(2026, 10, 5, 9, 1))
        self.assertEqual(len(self.sent(WEEKLY)), 1)
        self.assertEqual(self.state()['lastWeeklySummary'], '2026-10-04')

    def test_missed_summary_is_not_sent_after_monday(self):
        self.check(uk(2026, 10, 6, 9, 1))
        self.assertEqual(self.sent(WEEKLY), [])


class WeeklyVerdictTest(unittest.TestCase):
    SUNDAY = date(2026, 10, 4)

    def verdict(self, recorded):
        history = History('unused', {}, 'ZZ99ZZ')
        for offset in range(recorded):
            for draw in DRAWS:
                history.record(DrawResult(draw, self.SUNDAY - timedelta(days=offset), 'AA1 1AA', False))
        return summariseWeeklyResults(history, self.SUNDAY)[0].split('\n')[2]

    def test_distinguishes_no_wins_from_an_incomplete_week(self):
        self.assertEqual(self.verdict(0), "No wins were recorded this week. 63 of 63 draws weren't checked, "
                                          "so this week's results are incomplete.")
        self.assertEqual(self.verdict(3), "No wins were recorded this week. 36 of 63 draws weren't checked, "
                                          "so this week's results are incomplete.")
        self.assertEqual(self.verdict(7), "Unfortunately, you didn't have any wins this week. Better luck next week!")


class HistoryFileTest(CheckerTest):
    def write(self, data):
        os.makedirs(self.logs, exist_ok=True)
        with open(os.path.join(self.logs, 'pastData.json'), 'w') as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def legacyDay(self, mini='MI1 1AA', main='MA1 1AA'):
        draws = {k: {'hasWon': False, 'winningPostcode': 'XX1 1XX'} for k in
                 ('surveyDraw', 'videoDraw', 'bonusDrawFive', 'bonusDrawTen', 'bonusDrawTwenty')}
        draws['mainDraw'] = {'hasWon': main == POSTCODE, 'winningPostcode': main}
        draws['stackpotDraw'] = {'hasWon': False, 'winningPostcode': ['SA1 1AA', 'SB1 1BB']}
        draws['miniDraw'] = {'hasWon': mini == POSTCODE, 'winningPostcode': mini}
        return {'hasWon': POSTCODE in (mini, main), 'drawResults': draws}

    def test_version_1_history_is_migrated_without_losing_results(self):
        legacy = json.dumps({
            'lastBrowserLogin': '2026-10-01',
            '2026-09-21': self.legacyDay(),
            '2026-09-30': self.legacyDay(mini=POSTCODE),
            '2026-10-01': self.legacyDay(main=POSTCODE),
        })
        self.write(legacy)
        evening = uk(2026, 10, 1, 18, 1)
        self.deliver = lambda subject: subject != WIN
        self.check(evening, latestResults(evening, main=POSTCODE))

        state = self.state()
        self.assertEqual(state['version'], 2)
        self.assertEqual(state['postcode'], 'ZZ99ZZ')
        self.assertEqual(state['lastBrowserLogin'], '2026-10-01')
        self.assertEqual(state['draws']['2026-09-29']['miniDraw']['winningPostcode'], POSTCODE)  # 2pm saw last night's
        self.assertTrue(state['draws']['2026-09-29']['miniDraw']['hasWon'])
        self.assertEqual(state['draws']['2026-09-30']['stackpotDraw']['winningPostcode'], ['SA1 1AA', 'SB1 1BB'])
        self.assertEqual(state['draws']['2026-10-01']['miniDraw']['winningPostcode'], 'MI1 1AA')  # tonight's, new
        self.assertEqual(state['draws']['2026-09-30']['miniDraw']['winningPostcode'], 'MI1 1AA')  # from 1 Oct's 2pm
        self.assertNotIn('2026-09-21', state['draws'])  # ten-day retention
        [backup] = self.setAside('pastData.json.v1-backup-')
        with open(os.path.join(self.logs, backup)) as f:
            self.assertEqual(f.read(), legacy)

        # Version 1 never recorded delivery, so the still-open main draw win is sent; this attempt fails.
        self.assertEqual(len(self.sent(WIN)), run.EMAIL_ATTEMPTS)
        self.assertIn('Main Draw', self.sent(WIN)[0]['text'])
        self.assertNotIn('Mini Draw', self.sent(WIN)[0]['text'])  # the legacy Mini win closed at 2am
        self.assertIsNone(state['draws']['2026-10-01']['mainDraw']['notified'])
        self.assertIsNone(state['draws']['2026-09-29']['miniDraw']['notified'])

        self.deliver = True
        night = uk(2026, 10, 1, 21, 1)
        self.check(night, latestResults(night, main=POSTCODE))
        self.assertEqual(len(self.sent(WIN)), 1)
        self.assertTrue(self.entry('2026-10-01', 'mainDraw')['notified'])
        self.check(uk(2026, 10, 2, 9, 1), latestResults(night, main=POSTCODE), scheduled=False)
        self.assertEqual(self.sent(WIN), [])

    def test_corrupt_history_is_set_aside_and_checks_continue(self):
        self.write('{"version": 2, "draws": {')
        afternoon = uk(2026, 10, 1, 14, 0)
        self.check(afternoon, latestResults(afternoon, main=POSTCODE))
        self.assertEqual(len(self.sent(WIN)), 1)
        self.assertEqual(len(self.setAside('pastData.json.corrupt-')), 1)

    def test_changing_postcode_sets_the_old_history_aside(self):
        morning = uk(2026, 10, 1, 9, 1)
        both = latestResults(morning, stackpot=(POSTCODE, OTHER_POSTCODE))
        self.check(morning, both)
        self.assertEqual(len(self.sent(WIN)), 1)

        with mock.patch.dict(os.environ, {'YOUR_POSTCODE': OTHER_POSTCODE}):
            self.check(morning + timedelta(minutes=4), both)
        self.assertEqual(len(self.sent(WIN)), 1)  # the new postcode gets its own alert
        self.assertEqual(self.state()['postcode'], 'YY88YY')
        [old] = self.setAside('pastData.json.postcode-ZZ99ZZ-')
        self.assertTrue(self.state(old)['draws']['2026-10-01']['stackpotDraw']['notified'])

    def test_old_postcodes_unsent_wins_are_not_sent_after_a_change(self):
        afternoon = uk(2026, 10, 1, 14, 0)
        self.deliver = lambda subject: subject != WIN
        self.check(afternoon, latestResults(afternoon, main=POSTCODE))
        self.deliver = True
        with mock.patch.dict(os.environ, {'YOUR_POSTCODE': OTHER_POSTCODE}):
            self.check(uk(2026, 10, 1, 18, 1), ConnectionError('API down'))
        self.assertEqual(self.sent(WIN), [])
        self.assertEqual(len(self.sent(ERROR)), 1)
        self.assertEqual(self.state()['draws'], {})

    def test_case_and_spacing_changes_keep_the_same_history(self):
        afternoon = uk(2026, 10, 1, 14, 0)
        self.check(afternoon, latestResults(afternoon, main=POSTCODE))
        with mock.patch.dict(os.environ, {'YOUR_POSTCODE': ' zz99zz '}):
            self.check(uk(2026, 10, 1, 18, 1), latestResults(uk(2026, 10, 1, 18, 1), main=POSTCODE))
        self.assertEqual(self.sent(WIN), [])
        self.assertEqual(self.setAside('pastData.json.postcode-'), [])

    def test_concurrent_checks_wait_for_each_other(self):
        os.makedirs(self.logs, exist_ok=True)
        clock = FakeClock(uk(2026, 10, 1, 9, 1))
        self.payloads = [latestResults(clock.now())]
        worker = threading.Thread(target=lambda: run.main(scheduled=True, now=clock.now, sleep=clock.sleep))
        with redirect_stdout(io.StringIO()):
            with openHistory(os.path.join(self.logs, 'pastData.json'), POSTCODE):
                worker.start()
                worker.join(0.3)
                self.assertTrue(worker.is_alive())
                self.assertEqual(self.fetches, 0)
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.fetches, 1)
        self.assertIn('2026-10-01', self.state()['draws'])


class HealthCheckTest(CheckerTest):
    def healthCheck(self, payload):
        self.payloads = [payload]
        selenium = mock.Mock()
        selenium.json.return_value = {'value': {'ready': True}}
        output = io.StringIO()
        clock = FakeClock(uk(2026, 10, 1, 14, 0))
        with mock.patch('requests.get', return_value=selenium), \
                mock.patch.object(run, '_utcNow', clock.now), redirect_stdout(output):
            try:
                run.runTestCheck()
                code = 0
            except SystemExit as exit:
                code = exit.code
        return code, re.sub(r'\x1b\[[0-9;]*m', '', output.getvalue())

    def test_reports_each_draw_with_its_session_and_the_real_schedule(self):
        code, output = self.healthCheck(drawResults(mini=POSTCODE, miniAt='2026-09-30 18:00:00'))
        self.assertEqual(code, 0)
        self.assertIn('All systems operational', output)
        self.assertIn('Mini Draw', output)
        self.assertIn('Wed 30 Sep 18:00', output)
        self.assertIn('won · closed', output)
        self.assertNotIn('JACKPOT', output)
        self.assertIn('09:01, 14:00, 18:01 and 21:01 UK time', output)
        self.assertEqual(len(self.sent('Pick My Postcode — Thu 01 Oct results')), 1)
        self.assertFalse(os.path.exists(self.logs))  # the health check doesn't touch history

    def test_fails_when_a_draw_cannot_be_read(self):
        payload = drawResults()
        del payload['mini']
        code, output = self.healthCheck(payload)
        self.assertEqual(code, 1)
        self.assertIn("unavailable: Mini Draw (Wed 30 Sep 18:00)", output)

    def test_fails_and_reports_incomplete_results_when_the_api_is_stale(self):
        code, output = self.healthCheck(drawResults(midday='2026-09-29 12:00:00', stackpotAt='2026-09-29 09:00:00',
                                                    miniAt='2026-09-28 18:00:00'))
        self.assertEqual(code, 1)
        self.assertNotIn('All systems operational', output)
        self.assertIn('Failed checks: api', output)
        self.assertIn("incomplete, so this isn't a confirmed no-win", output)
        self.assertNotIn('What happens next', output)
        [summary] = self.sent('Pick My Postcode — Thu 01 Oct results')
        self.assertNotIn('working perfectly', summary['text'])
        self.assertIn('unavailable: Main Draw (Thu 01 Oct 12:00)', summary['text'])


class CommandLineTest(unittest.TestCase):
    def test_help_describes_the_modes_without_running_a_check(self):
        result = subprocess.run([sys.executable, 'run.py', '--help'], cwd=REPO, capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--test', result.stdout)
        self.assertIn('09:01, 14:00, 18:01 and 21:01 UK time', result.stdout)


if __name__ == '__main__':
    unittest.main()
