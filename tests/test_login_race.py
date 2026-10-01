"""The homepage race that FakeSite cannot see: registration and sign-in share field ids, and the
sign-in panel is still hidden on the first postcode lookup.

Needs a real browser because the offline fakes key elements by the locator string, so they follow
whatever SIGN_IN_FORM currently is. Set SELENIUM_TEST_URL to a Selenium hub (for example
http://127.0.0.1:4444/wd/hub). The page is a data URL and the credentials are synthetic, so the
offline suite stays network-free and this test never touches the live site.
"""
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import browserLogin
from browserLogin import SIGNED_IN, signIn
from tests.support import POSTCODE
from tests.test_browser import CREDENTIALS

# document.evaluate runs once per lookup in this Selenium. The first postcode lookup still sees the
# sign-in panel hidden and arms the reveal; the next lookup shows the panel before searching. That
# is the live gap, without a sleep: the postcode is typed while only registration is displayed, and
# the email lookup finds the sign-in form already open.
_PAGE = """<!DOCTYPE html>
<html><head><title>Fixture</title></head><body>
<button type="button">Sign in</button>
<div id="sign-in-panel" hidden>
  <form id="login-form">
    <input id="postcode">
    <input id="email">
    <button type="submit">Sign in</button>
  </form>
</div>
<form id="registration-form">
  <input id="postcode">
  <input id="email">
  <button type="submit">Register</button>
</form>
<script>
window.__submitted = null;
let arm = false;
let revealed = false;
let signInHiddenAtFirstPostcodeLookup = null;
const orig = Document.prototype.evaluate;
Document.prototype.evaluate = function (expression) {
  const text = String(expression);
  if (arm && !revealed) {
    revealed = true;
    document.getElementById('sign-in-panel').hidden = false;
  }
  const result = orig.apply(this, arguments);
  if (!arm && text.indexOf('postcode') !== -1) {
    arm = true;
    signInHiddenAtFirstPostcodeLookup = document.getElementById('sign-in-panel').hidden;
  }
  return result;
};
function fields(form) {
  const found = {postcode: '', email: ''};
  for (const input of form.getElementsByTagName('input')) found[input.id] = input.value;
  return found;
}
window.__state = function () {
  return {
    login: fields(document.getElementById('login-form')),
    registration: fields(document.getElementById('registration-form')),
    submitted: window.__submitted,
    signInHiddenAtFirstPostcodeLookup: signInHiddenAtFirstPostcodeLookup
  };
};
function remember(form, name) {
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    const found = fields(form);
    window.__submitted = {form: name, postcode: found.postcode, email: found.email};
    if (name === 'login' && found.postcode !== '' && found.email !== '') {
      const link = document.createElement('a');
      link.href = '/api/index.php/logout';
      link.textContent = 'Logout';
      document.body.appendChild(link);
    }
  });
}
remember(document.getElementById('login-form'), 'login');
remember(document.getElementById('registration-form'), 'registration');
</script>
</body></html>"""


def _page_url():
    return 'data:text/html;charset=utf-8,' + quote(_PAGE)


def _browser(hub_url):
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    return webdriver.Remote(command_executor=hub_url, options=options)


@unittest.skipUnless(os.environ.get('SELENIUM_TEST_URL'),
                     'set SELENIUM_TEST_URL to a Selenium hub to run the login-form fixture')
class SignInFormRaceTest(unittest.TestCase):
    def test_types_into_the_sign_in_form_not_the_visible_registration_form(self):
        driver = _browser(os.environ['SELENIUM_TEST_URL'])
        try:
            with mock.patch.object(browserLogin, 'SITE', _page_url()), mock.patch.dict(os.environ, CREDENTIALS):
                try:
                    with redirect_stdout(StringIO()):
                        signIn(driver, wait_seconds=5, signed_in_seconds=3)
                except RuntimeError as error:
                    state = driver.execute_script('return window.__state()')
                    self.fail(f'{error}; forms were {state}')
            state = driver.execute_script('return window.__state()')
            self.assertIs(state['signInHiddenAtFirstPostcodeLookup'], True)
            self.assertEqual(state['submitted'], {
                'form': 'login', 'postcode': POSTCODE, 'email': CREDENTIALS['PMP_EMAIL']})
            self.assertEqual(state['registration'], {'postcode': '', 'email': ''})
            self.assertTrue(driver.find_elements(By.XPATH, SIGNED_IN))
        finally:
            driver.quit()
