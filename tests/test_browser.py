import io
import os
import subprocess
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from selenium.common.exceptions import NoSuchElementException, WebDriverException

import browserLogin
from browserLogin import SIGN_IN_BUTTON, SIGN_IN_FORM, SIGNED_IN, SITE, signIn
from tests.support import POSTCODE, stalledSeleniumServer

CREDENTIALS = {'YOUR_POSTCODE': POSTCODE, 'PMP_EMAIL': 'someone@example.com'}

class FakeElement:
    def __init__(self, onClick=None, shown=True):
        self.onClick, self.shown, self.typed = onClick, shown, []

    def is_displayed(self):
        return self.shown

    def is_enabled(self):
        return True

    def click(self):
        if self.onClick:
            self.onClick()

    def send_keys(self, text):
        self.typed.append(text)


class FakeSite:
    """The site's sign-in flow as a WebDriver: 'Sign in' opens the form, and submitting it reloads the
    page signed in `delay` seconds later, unless the details are rejected."""
    title = 'Pick My Postcode'

    def __init__(self, accept=True, delay=0.0):
        self.accept, self.delay = accept, delay
        self.signedInAt = None
        self.visited = []  # (url, signed in when visited)
        self.formOpen = False
        self.postcode, self.email = FakeElement(), FakeElement()
        self.elements = {
            SIGN_IN_BUTTON: [FakeElement(shown=False), FakeElement(self._openForm)],
            f"{SIGN_IN_FORM}//input[@id='postcode']": [self.postcode],
            f"{SIGN_IN_FORM}//input[@id='email']": [self.email],
            f"{SIGN_IN_FORM}//button[@type='submit']": [FakeElement(self._submit)],
        }

    def _openForm(self):
        self.formOpen = True

    def _submit(self):
        if self.accept:
            self.signedInAt = time.monotonic() + self.delay

    def signedIn(self):
        return self.signedInAt is not None and time.monotonic() >= self.signedInAt

    def get(self, url):
        self.visited.append((url, self.signedIn()))

    def find_elements(self, by, xpath):
        if xpath == SIGNED_IN:
            return [FakeElement()] if self.signedIn() else []
        if xpath.startswith(SIGN_IN_FORM) and not self.formOpen:
            return []
        return self.elements.get(xpath, [])

    def find_element(self, by, xpath):
        found = self.find_elements(by, xpath)
        if not found:
            raise NoSuchElementException(xpath)
        return found[0]


class SignInTest(unittest.TestCase):
    def setUp(self):
        for patcher in (mock.patch.dict(os.environ, CREDENTIALS), mock.patch.object(browserLogin, 'sleep')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_(self, site, **timeouts):
        with redirect_stdout(io.StringIO()):
            signIn(site, wait_seconds=2, **timeouts)
            browserLogin.visitDrawPages(site)

    def test_waits_for_a_delayed_sign_in_before_visiting_the_draw_pages(self):
        site = FakeSite(delay=0.6)
        self.run_(site, signed_in_seconds=5)
        self.assertEqual(site.postcode.typed, ['ZZ9 9ZZ'])
        self.assertEqual(site.email.typed, ['someone@example.com'])
        self.assertEqual(site.visited, [(SITE, False)] + [(SITE + path, True) for _, path, _ in browserLogin.DRAW_PAGES])

    def test_rejected_details_fail_without_visiting_the_draw_pages(self):
        site = FakeSite(accept=False)
        with self.assertRaisesRegex(RuntimeError, "didn't show you as signed in.*YOUR_POSTCODE and PMP_EMAIL"):
            self.run_(site, signed_in_seconds=1)
        self.assertEqual(site.visited, [(SITE, False)])

    def test_screenshot_and_close_failures_do_not_hide_the_original_error(self):
        driver = mock.Mock()
        driver.get.side_effect = WebDriverException('net::ERR_NAME_NOT_RESOLVED')
        driver.save_screenshot.side_effect = WebDriverException('session gone')
        driver.quit.side_effect = WebDriverException('session gone')
        with mock.patch.object(browserLogin, '_connect', return_value=driver), redirect_stdout(io.StringIO()) as out:
            with self.assertRaisesRegex(WebDriverException, 'ERR_NAME_NOT_RESOLVED'):
                browserLogin._run('/nonexistent/error_screenshot.png')
        driver.quit.assert_called_once()
        self.assertIn("Couldn't save a screenshot", out.getvalue())
        self.assertIn("Couldn't close the browser", out.getvalue())


class TimeLimitTest(unittest.TestCase):
    def test_a_stalled_selenium_server_is_cut_off_at_the_time_limit(self):
        with stalledSeleniumServer() as (server, url), mock.patch.dict(os.environ, {'SELENIUM_URL': url}):
            started = time.monotonic()
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(TimeoutError, 'stopped after 2 seconds'):
                browserLogin.browserLogin(time_limit=2)
            self.assertLess(time.monotonic() - started, 10)

            # The browser process was really stopped: its stalled request to the server has been closed.
            server.settimeout(5)
            connection, _ = server.accept()
            with connection:
                connection.settimeout(5)
                while connection.recv(65536):
                    pass

    def test_a_failed_run_reports_its_final_error(self):
        output = "Signing in\nTraceback (most recent call last):\nRuntimeError: The site didn't show you as signed in\n"
        failed = subprocess.CompletedProcess([], 1, stdout=output)
        with mock.patch.object(browserLogin.subprocess, 'run', return_value=failed), \
                redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(RuntimeError) as raised:
                browserLogin.browserLogin()
        self.assertEqual(str(raised.exception), "RuntimeError: The site didn't show you as signed in")
        self.assertIn('Signing in', out.getvalue())


if __name__ == '__main__':
    unittest.main()
