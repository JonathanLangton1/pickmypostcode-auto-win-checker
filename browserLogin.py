"""Signs in to pickmypostcode.com in the Selenium Chrome and visits the draw pages for the daily bonus."""
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import subprocess
import sys
from time import sleep

SITE = 'https://pickmypostcode.com/'
TIME_LIMIT_SECONDS = 300      # the whole browser run, including closing the browser
REQUEST_TIMEOUT_SECONDS = 60  # each request to the Selenium server
PAGE_LOAD_TIMEOUT_SECONDS = 60
WAIT_SECONDS = 20
SIGNED_IN_SECONDS = 30
DRAW_PAGES = (('Video Draw', 'video/', 1), ('Survey Draw', 'survey-draw/', 0.5),
              ('Stackpot Draw', 'stackpot/', 0.5), ('Bonus Draw', 'your-bonus/', 0.5))

# Several "Sign in" buttons can be in the page (nav, draw banners, a hidden mobile menu); any visible one
# opens the sign-in form. The site reloads the page after a successful sign-in, and only then shows the
# account menu, whose Logout link is the signal that it worked.
SIGN_IN_BUTTON = "//button[normalize-space()='Sign in']"
SIGN_IN_FORM = "//form[.//input[@id='postcode'] and .//input[@id='email']]"
SIGNED_IN = "//a[contains(@href, '/api/index.php/logout')]"


def browserLogin(time_limit=TIME_LIMIT_SECONDS):
    """Run the browser in a child process that is killed after `time_limit` seconds, so a stalled
    Selenium server can't hold up later checks. Raises if it didn't confirm the sign-in."""
    try:
        finished = subprocess.run([sys.executable, os.path.abspath(__file__)], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, timeout=time_limit,
                                  env={**os.environ, 'PYTHONUNBUFFERED': '1'})
    except subprocess.TimeoutExpired as expired:
        output = _echo(expired.output)
        raise TimeoutError(f'The browser was stopped after {time_limit} seconds '
                           f'(last output: {_lastLine(output) or "none"})') from None
    output = _echo(finished.stdout)
    if finished.returncode:
        raise RuntimeError(_lastLine(output) or f'The browser exited with code {finished.returncode}')


def _echo(output):
    """Print the child's output (bytes after a timeout) and return it as text."""
    if isinstance(output, bytes):
        output = output.decode(errors='replace')
    if output:
        print(output, end='' if output.endswith('\n') else '\n')
    return output or ''


def _lastLine(output):
    lines = output.strip().splitlines()
    return lines[-1] if lines else ''


def _run(screenshot_path):
    driver = _connect()
    try:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
        signIn(driver)
        visitDrawPages(driver)
    except Exception as error:
        print(f"An error occurred: {error}")
        try:
            driver.save_screenshot(screenshot_path)
        except Exception as screenshot_error:
            print(f"Couldn't save a screenshot: {screenshot_error}")
        raise
    finally:
        print('Closing browser')
        try:
            driver.quit()
        except Exception as quit_error:
            print(f"Couldn't close the browser: {quit_error}")


def _connect():
    selenium_url = os.getenv("SELENIUM_URL", "http://selenium-chrome:4444/wd/hub")
    chrome_options = Options()
    if os.getenv("HEADLESS", "true").lower() != "false":
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    RemoteConnection.set_timeout(REQUEST_TIMEOUT_SECONDS)  # Selenium 4.25 otherwise waits forever

    for _ in range(10):  # the Selenium server may still be starting
        try:
            return webdriver.Remote(command_executor=selenium_url, options=chrome_options)
        except Exception as error:
            last_error = error
            print("Selenium server is not ready yet. Retrying in 2 seconds...")
            sleep(2)
    raise RuntimeError(f"Failed to connect to Selenium server after multiple attempts: {last_error}")


def signIn(driver, wait_seconds=WAIT_SECONDS, signed_in_seconds=SIGNED_IN_SECONDS):
    driver.get(SITE)
    print(f"Page title after loading: {driver.title}")
    wait = WebDriverWait(driver, wait_seconds, ignored_exceptions=(NoSuchElementException, StaleElementReferenceException))
    print('Signing in')
    wait.until(_visible(SIGN_IN_BUTTON)).click()
    wait.until(_visible(f"{SIGN_IN_FORM}//input[@id='postcode']")).send_keys(os.environ.get("YOUR_POSTCODE"))
    wait.until(_visible(f"{SIGN_IN_FORM}//input[@id='email']")).send_keys(os.environ.get("PMP_EMAIL"))
    wait.until(_visible(f"{SIGN_IN_FORM}//button[@type='submit']")).click()
    try:
        WebDriverWait(driver, signed_in_seconds, ignored_exceptions=(NoSuchElementException, StaleElementReferenceException)
                      ).until(EC.presence_of_element_located((By.XPATH, SIGNED_IN)))
    except TimeoutException:
        raise RuntimeError(f"The site didn't show you as signed in after {signed_in_seconds} seconds; "
                           "check YOUR_POSTCODE and PMP_EMAIL") from None
    print('Signed in')


def visitDrawPages(driver):
    for name, path, pause in DRAW_PAGES:
        print(f"Requesting {name} Page")
        driver.get(SITE + path)
        sleep(pause)


def _visible(xpath):
    """Waits for the first element at `xpath` that is shown and enabled."""
    def find(driver):
        return next((e for e in driver.find_elements(By.XPATH, xpath) if e.is_displayed() and e.is_enabled()), False)
    return find


if __name__ == "__main__":
    _run(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'error_screenshot.png'))
