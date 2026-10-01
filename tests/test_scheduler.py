import io
import os
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest import mock

from scheduler import nextCheck, runForever
from tests.support import FakeClock, uk


class Stop(BaseException):
    pass


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        # The schedule must follow UK time whatever the host's timezone is.
        original = os.environ.get('TZ')
        os.environ['TZ'] = 'Asia/Tokyo'
        time.tzset()

        def restore():
            if original is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = original
            time.tzset()
        self.addCleanup(restore)

    def runChecks(self, start, count, check=None, withRetry=False, takes=0):
        """Times of the first `count` checks, each taking `takes` seconds; `check(retry)` supplies its result."""
        clock = FakeClock(start)
        runs = []

        def fakeCheck(retry):
            runs.append((clock.now(), retry) if withRetry else clock.now())
            if len(runs) == count:
                raise Stop
            clock.sleep(takes)
            return check(retry) if check else False

        with redirect_stdout(io.StringIO()), self.assertRaises(Stop):
            runForever(fakeCheck, now=clock.now, sleep=clock.sleep)
        return runs

    def test_checks_at_startup_then_at_uk_check_times_across_the_october_clock_change(self):
        runs = self.runChecks(uk(2026, 10, 24, 20, 0), 6)
        self.assertEqual(runs, [
            utc(2026, 10, 24, 19, 0),   # startup, Sat 20:00 BST
            utc(2026, 10, 24, 20, 1),   # Sat 21:01 BST
            utc(2026, 10, 25, 9, 1),    # Sun 09:01 GMT
            utc(2026, 10, 25, 14, 0),
            utc(2026, 10, 25, 18, 1),
            utc(2026, 10, 25, 21, 1),
        ])

    def test_follows_uk_time_across_the_march_clock_change(self):
        runs = self.runChecks(uk(2026, 3, 28, 22, 0), 3)
        self.assertEqual(runs[1:], [utc(2026, 3, 29, 8, 1), utc(2026, 3, 29, 13, 0)])  # 09:01, 14:00 BST

    def test_a_failing_check_does_not_stop_the_schedule(self):
        def boom(retry):
            raise RuntimeError('check crashed')
        with mock.patch('traceback.print_exc'):
            runs = self.runChecks(uk(2026, 10, 1, 9, 0), 3, check=boom)
        self.assertEqual(runs[1:], [uk(2026, 10, 1, 9, 1), uk(2026, 10, 1, 14, 0)])

    def test_a_check_asking_for_a_retry_is_retried_every_five_minutes_until_it_succeeds(self):
        outcomes = iter([True, True, True, False])
        runs = self.runChecks(uk(2026, 10, 1, 21, 1), 5, check=lambda retry: next(outcomes), withRetry=True)
        self.assertEqual(runs, [
            (uk(2026, 10, 1, 21, 1), False),
            (uk(2026, 10, 1, 21, 6), True),
            (uk(2026, 10, 1, 21, 11), True),
            (uk(2026, 10, 1, 21, 16), True),
            (uk(2026, 10, 2, 9, 1), False),
        ])

    def test_a_check_that_runs_past_a_check_time_is_followed_by_that_check_at_once(self):
        runs = self.runChecks(uk(2026, 10, 1, 20, 59), 3, takes=240, withRetry=True)
        self.assertEqual(runs, [(uk(2026, 10, 1, 20, 59), False), (uk(2026, 10, 1, 21, 3), False),
                                (uk(2026, 10, 2, 9, 1), False)])

    def test_an_overrunning_check_asking_for_a_retry_still_runs_the_overdue_normal_check(self):
        runs = self.runChecks(uk(2026, 10, 1, 20, 59), 3, check=lambda retry: True, takes=240, withRetry=True)
        self.assertEqual(runs, [(uk(2026, 10, 1, 20, 59), False), (uk(2026, 10, 1, 21, 3), False),
                                (uk(2026, 10, 1, 21, 12), True)])

    def test_a_retry_due_after_the_next_normal_check_is_left_to_it(self):
        runs = self.runChecks(uk(2026, 10, 1, 13, 57), 3, check=lambda retry: True, withRetry=True)
        self.assertEqual(runs, [(uk(2026, 10, 1, 13, 57), False), (uk(2026, 10, 1, 14, 0), False),
                                (uk(2026, 10, 1, 14, 5), True)])

    def test_next_check_is_strictly_after_now(self):
        self.assertEqual(nextCheck(uk(2026, 10, 1, 9, 1)), uk(2026, 10, 1, 14, 0))
        self.assertEqual(nextCheck(uk(2026, 10, 1, 21, 30)), uk(2026, 10, 2, 9, 1))


if __name__ == '__main__':
    unittest.main()
