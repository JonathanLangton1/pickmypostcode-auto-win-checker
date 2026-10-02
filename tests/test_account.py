"""The daily account check against scripted HTTP responses. No network and no mail."""
import io
import json
import os
import tempfile
import traceback
import unittest
from contextlib import redirect_stdout
from datetime import datetime, time, timedelta
from unittest import mock

import requests

import accountCheck
import run
from accountCheck import API_BASE, AccountCheckError, creditDay, dailyAccountCheck
from draws import UK
from tests.support import POSTCODE, latestResults, uk

EMAIL = 'person@example.com'
ENV = {'PMP_EMAIL': EMAIL, 'YOUR_POSTCODE': POSTCODE}
STAMP = '%Y-%m-%d %H:%M:%S'
SECRET = 'SECRET-VALUE'


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self.is_redirect = 300 <= status < 400
        self._payload = payload

    def json(self):
        if self.status_code != 200:
            raise AssertionError('response body was read')
        return self._payload


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.closed = False
        self.max_redirects = None

    def request(self, method, url, json=None, timeout=None, allow_redirects=True, **extra):
        self.calls.append({'method': method, 'url': url, 'json': json, 'timeout': timeout,
                           'allow_redirects': allow_redirects, 'extra': extra})
        status, payload = self.handler(method, url, json)
        return FakeResponse(status, payload)

    def close(self):
        self.closed = True


class Site:
    """A synthetic account. Visits add one penny unless that draw is already in the period."""

    def __init__(self, when, credited=False):
        self.when = when
        self.slugs = ('main', 'video', 'survey')
        self.bonus = 1156
        self.counters = {name: 20 + index for index, name in enumerate(self.slugs)}
        start = datetime.combine(creditDay(when), time(12), tzinfo=UK)
        # Keep an already-credited stamp inside this period, including a check at exactly noon.
        credited_at = min(start + timedelta(minutes=5), when.astimezone(UK))
        fresh = (credited_at if credited_at >= start else start).strftime(STAMP)
        stale = (start - timedelta(hours=1)).strftime(STAMP)
        self.stamps = {name: fresh if credited else stale for name in self.slugs}
        self.login_stamps = {name: (start - timedelta(days=1)).strftime(STAMP) for name in self.slugs}
        self.identity = (EMAIL, POSTCODE)
        self.logged_in = True
        self.status = 'active'
        self.holiday = 0
        self.activationkey = ''
        self.activated = None
        self.include_activation = True
        self.login_error = ''
        self.token = None
        self.freeze = False
        self.stamp_only = False
        self.fail_on = None
        self.fail_status = 500
        self.login_payload = None

    def __call__(self, method, url, payload):
        path = url[len(API_BASE):]
        if path == 'token/put/user':
            self._method('POST', method)
            data = {'error': 'User must be logged in to generate token'}
            if self.token:
                data['token'] = self.token
            return 200, {'status': 'error', 'data': data}
        if path == 'login/':
            self._method('POST', method)
            self.login_payload = payload
            return 200, self._body(self.login_stamps, [], True, login=True)
        if path == 'user/current/':
            self._method('GET', method)
            return 200, self._body(self.stamps, {'added': False, 'page': None}, False)
        for slug, page_id in (('main', 27079), ('video', 23645), ('survey', 21851)):
            if path == f'user/current/{slug}/{page_id}':
                self._method('GET', method)
                if self.fail_on == slug:
                    return self.fail_status, {'body': SECRET}
                self._credit(slug)
                return 200, self._body(self.stamps, {'added': self.added[slug], 'page': slug}, False)
        raise AssertionError(path)

    def _method(self, expected, method):
        if method != expected:
            raise AssertionError(method)

    def _credit(self, slug):
        if not hasattr(self, 'added'):
            self.added = {}
        stamp = self.stamps[slug]
        start = datetime.combine(creditDay(self.when), time(12), tzinfo=UK)
        already = (not self.freeze and isinstance(stamp, str)
                   and datetime.strptime(stamp, STAMP).replace(tzinfo=UK) >= start)
        if self.stamp_only:
            self.added[slug] = False
            self.stamps[slug] = self.when.astimezone(UK).strftime(STAMP)
            return
        if already:
            self.added[slug] = False
            return
        if self.freeze or stamp is None:
            self.added[slug] = False
            return
        self.added[slug] = True
        self.counters[slug] += 1
        self.bonus += 1
        self.stamps[slug] = self.when.astimezone(UK).strftime(STAMP)

    def _body(self, stamps, penny, cached, login=False):
        raw = {'loggedIn': self.logged_in, 'email': self.identity[0], 'postcode': self.identity[1],
               'status': self.status, 'holiday': self.holiday, 'totalBonus': self.bonus}
        if self.include_activation:
            raw['activationkey'] = self.activationkey
            raw['activated'] = self.activated
        for slug in self.slugs:
            raw[f'{slug}draw'] = self.counters[slug]
            raw[f'{slug}updated'] = stamps[slug]
        data = {'user': {'cached': cached, 'data': raw}, 'penny': penny}
        if login:
            data['error'] = self.login_error
        return {'status': 'success', 'data': data}


class AccountApiTest(unittest.TestCase):
    def check(self, handler, when):
        session = FakeSession(handler)
        with mock.patch.dict(os.environ, ENV), mock.patch('accountCheck.requests.Session', return_value=session):
            try:
                return dailyAccountCheck(now=lambda: when), session
            finally:
                self.assertTrue(session.closed)

    def fail(self, handler, when):
        try:
            self.check(handler, when)
        except AccountCheckError as error:
            text = f'{error}\n{traceback.format_exc()}'
            self.assertNotIn(SECRET, text)
            self.assertNotIn(EMAIL, text)
            self.assertNotIn(POSTCODE, text)
            self.assertIsNone(error.__cause__)
            return error
        self.fail('expected AccountCheckError')

    def assertBounded(self, session):
        self.assertEqual(session.max_redirects, 0)
        self.assertGreaterEqual(len(session.calls), 1)
        for call in session.calls:
            self.assertEqual(call['timeout'], (accountCheck.CONNECT_TIMEOUT, accountCheck.READ_TIMEOUT))
            self.assertFalse(call['allow_redirects'])
            self.assertEqual(call['extra'], {})
            self.assertNotIn('stackpot', call['url'])
            self.assertNotIn('21674', call['url'])
            self.assertNotIn('1266', call['url'])

    def test_new_credits_ignore_a_cached_login_and_verify_each_draw(self):
        when = uk(2026, 10, 2, 14, 1)
        site = Site(when)
        result, session = self.check(site, when)
        self.assertEqual((result.new_credits, result.total_bonus, result.verified_day), (3, 1159, when.date()))
        self.assertIsNone(site.login_payload.get('token') if 'token' in site.login_payload else None)
        self.assertEqual(set(site.login_payload), {'email', 'postcode'})
        self.assertBounded(session)
        self.assertEqual([call['url'][len(API_BASE):] for call in session.calls], [
            'token/put/user', 'login/', 'user/current/',
            'user/current/main/27079', 'user/current/video/23645', 'user/current/survey/21851',
            'user/current/',
        ])
        self.assertNotEqual(site.login_stamps, site.stamps)

    def test_token_is_sent_only_when_the_token_call_returns_one(self):
        when = uk(2026, 10, 2, 14, 1)
        site = Site(when, credited=True)
        site.token = SECRET
        result, session = self.check(site, when)
        self.assertEqual(result.new_credits, 0)
        self.assertEqual(site.login_payload['token'], SECRET)
        self.assertNotIn(SECRET, [call['url'] for call in session.calls])

    def test_already_credited_legacy_account_is_success(self):
        when = uk(2026, 10, 2, 14, 1)
        site = Site(when, credited=True)
        site.include_activation = False
        site.identity = ('Person@Example.com', 'zz99zz')
        result, session = self.check(site, when)
        self.assertEqual(result.new_credits, 0)
        self.assertEqual(result.total_bonus, 1156)
        self.assertEqual(result.verified_day, when.date())
        self.assertEqual(len(session.calls), 7)

    def test_verified_day_follows_the_noon_boundary(self):
        before, after = uk(2026, 10, 2, 11, 30), uk(2026, 10, 2, 12, 0)
        early, _session = self.check(Site(before, credited=True), before)
        later, _session = self.check(Site(after, credited=True), after)
        self.assertEqual(early.verified_day.isoformat(), '2026-10-01')
        self.assertEqual(later.verified_day.isoformat(), '2026-10-02')

    def test_sign_in_failure_and_wrong_identity_hide_the_response(self):
        when = uk(2026, 10, 2, 14, 1)
        rejected = Site(when)
        rejected.login_error = f'password for {SECRET}'
        self.assertEqual(str(self.fail(rejected, when)), 'sign-in failed')

        other = Site(when)
        other.identity = (f'{SECRET}@example.com', POSTCODE)
        self.assertEqual(str(self.fail(other, when)), 'signed-in account does not match')

        swapped = Site(when)
        swapped.identity = (EMAIL, POSTCODE)

        def swap(method, url, payload):
            status, body = swapped(method, url, payload)
            if url.endswith('login/'):
                swapped.identity = (f'{SECRET}@example.com', 'AA1 1AA')
            return status, body

        self.assertEqual(str(self.fail(swap, when)), 'signed-in account does not match')

    def test_inactive_holiday_and_activation_key_fail(self):
        when = uk(2026, 10, 2, 14, 1)
        inactive = Site(when, credited=True)
        inactive.status = 'suspended'
        self.assertEqual(str(self.fail(inactive, when)), 'account is not active')
        away = Site(when, credited=True)
        away.holiday = 1
        self.assertEqual(str(self.fail(away, when)), 'account is on holiday')
        pending = Site(when, credited=True)
        pending.activationkey = SECRET
        self.assertEqual(str(self.fail(pending, when)), 'account is not activated')

    def test_stale_or_missing_draw_timestamp_is_not_success(self):
        when = uk(2026, 10, 2, 14, 1)
        stale = Site(when)
        stale.freeze = True
        self.assertEqual(str(self.fail(stale, when)), 'draw timestamp is missing or stale')
        missing = Site(when)
        missing.stamps['main'] = None
        self.assertEqual(str(self.fail(missing, when)), 'draw timestamp is missing or stale')

    def test_redirect_is_refused_without_retry_or_reading_the_body(self):
        when = uk(2026, 10, 2, 14, 1)

        def redirect(method, url, payload):
            if url.endswith('token/put/user'):
                return 200, {'status': 'error', 'data': {'error': 'User must be logged in to generate token'}}
            return 302, {'body': SECRET}

        calls = self._calls(redirect, when)
        self.assertEqual([call['url'][len(API_BASE):] for call in calls], ['token/put/user', 'login/'])
        self.assertEqual(str(self.fail(redirect, when)), 'account API redirect refused')

    def _calls(self, handler, when):
        session = FakeSession(handler)
        with mock.patch.dict(os.environ, ENV), mock.patch('accountCheck.requests.Session', return_value=session):
            with self.assertRaises(AccountCheckError):
                dailyAccountCheck(now=lambda: when)
        self.assertTrue(session.closed)
        return session.calls

    def test_a_timeout_is_retried_once_and_then_reported_without_the_transport_error(self):
        when = uk(2026, 10, 2, 14, 1)
        attempts = {'n': 0}

        def timeout(method, url, payload):
            attempts['n'] += 1
            raise requests.Timeout(f'read timed out {SECRET}')

        error = self.fail(timeout, when)
        self.assertEqual(str(error), 'account API timed out')
        self.assertEqual(attempts['n'], accountCheck.ATTEMPTS)

        site = Site(when)
        attempts['n'] = 0

        def once(method, url, payload):
            if url.endswith('token/put/user') and attempts['n'] == 0:
                attempts['n'] += 1
                raise requests.Timeout(SECRET)
            return site(method, url, payload)

        result, session = self.check(once, when)
        self.assertEqual(result.new_credits, 3)
        self.assertEqual(sum(call['url'].endswith('token/put/user') for call in session.calls), 2)

    def test_a_timed_out_visit_keeps_a_saved_credit_and_finishes_the_other_draws(self):
        when = uk(2026, 10, 2, 14, 1)
        site = Site(when)
        calls = {'main': 0}

        def handler(method, url, payload):
            if url.endswith('/user/current/main/27079'):
                calls['main'] += 1
                site._credit('main')  # the server saved the penny
                if calls['main'] == 1:
                    raise requests.Timeout('saved then timed out')
            return site(method, url, payload)

        result, session = self.check(handler, when)
        self.assertEqual(calls['main'], 2)
        self.assertEqual((result.new_credits, result.total_bonus, result.verified_day), (3, 1159, when.date()))
        self.assertIn(API_BASE + 'user/current/survey/21851', [call['url'] for call in session.calls])

        fresh = Site(when)
        calls['main'] = 0

        def again(method, url, payload):
            if url.endswith('/user/current/main/27079'):
                calls['main'] += 1
                fresh._credit('main')
                if calls['main'] == 1:
                    raise requests.Timeout('saved then timed out')
            return fresh(method, url, payload)

        session = FakeSession(again)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        logs = os.path.join(tmp.name, 'logs')
        with mock.patch.object(run, 'LOGS_DIR', logs), \
                mock.patch.object(run, 'fetchDraws', return_value=latestResults(when)), \
                mock.patch.object(run, 'sendEmail', return_value=True), \
                mock.patch.object(run, '_errorSentFor', None), \
                mock.patch.dict(os.environ, {**ENV, 'NOTIFICATION_EMAIL_ADDRESS': 'me@example.com'}), \
                mock.patch('accountCheck.requests.Session', return_value=session), \
                redirect_stdout(io.StringIO()):
            run.main(scheduled=True, now=lambda: when, sleep=lambda _seconds: None)
        with open(os.path.join(logs, 'pastData.json')) as history_file:
            self.assertEqual(json.load(history_file)['lastAccountCheck'], '2026-10-02')

    def test_added_false_without_a_new_counter_is_not_a_saved_credit(self):
        when = uk(2026, 10, 2, 14, 1)
        site = Site(when)
        site.stamp_only = True
        self.assertEqual(str(self.fail(site, when)), 'draw activity was not verified')

    def test_no_request_is_started_after_the_budget(self):
        when = uk(2026, 10, 2, 14, 1)

        def explode(method, url, payload):
            raise AssertionError('request started')

        with mock.patch('accountCheck.monotonic', side_effect=[0, accountCheck.OVERALL_SECONDS + 1]):
            error = self.fail(explode, when)
        self.assertEqual(str(error), 'account request budget is used')

    def test_missing_credentials_do_not_open_a_session(self):
        when = uk(2026, 10, 2, 14, 1)
        with mock.patch.dict(os.environ, {'PMP_EMAIL': '', 'YOUR_POSTCODE': POSTCODE}), \
                mock.patch('accountCheck.requests.Session') as session:
            with self.assertRaises(AccountCheckError) as caught:
                dailyAccountCheck(now=lambda: when)
        self.assertEqual(str(caught.exception), 'account credentials are not set')
        session.assert_not_called()


class PartialReceiptTest(unittest.TestCase):
    def test_a_failed_draw_visit_does_not_save_the_receipt(self):
        when = uk(2026, 10, 2, 14, 0)
        site = Site(when)
        site.fail_on = 'video'
        session = FakeSession(site)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        logs = os.path.join(tmp.name, 'logs')
        emails = []

        def send(to, subject, message, html_message):
            emails.append((subject, message))
            return True

        with mock.patch.object(run, 'LOGS_DIR', logs), \
                mock.patch.object(run, 'fetchDraws', return_value=latestResults(when, main=POSTCODE)), \
                mock.patch.object(run, 'sendEmail', side_effect=send), \
                mock.patch.dict(os.environ, {**ENV, 'NOTIFICATION_EMAIL_ADDRESS': 'me@example.com'}), \
                mock.patch('accountCheck.requests.Session', return_value=session), \
                redirect_stdout(io.StringIO()):
            run.main(scheduled=True, now=lambda: when, sleep=lambda _seconds: None)

        with open(os.path.join(logs, 'pastData.json')) as history:
            state = json.load(history)
        self.assertIsNone(state['lastAccountCheck'])
        self.assertTrue(state['draws']['2026-10-02']['mainDraw']['hasWon'])
        self.assertTrue(state['draws']['2026-10-02']['mainDraw']['notified'])
        blob = '\n'.join(part for email in emails for part in email)
        self.assertIn('HTTP 500', blob)
        self.assertNotIn(SECRET, blob)
        self.assertIn('You have won', emails[0][0])
        urls = [call['url'] for call in session.calls]
        self.assertEqual(urls.count(API_BASE + 'user/current/video/23645'), 1)
        self.assertNotIn(API_BASE + 'user/current/survey/21851', urls)
        self.assertTrue(session.closed)


if __name__ == '__main__':
    unittest.main()
