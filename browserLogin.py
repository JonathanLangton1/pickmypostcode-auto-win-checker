from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import json
from datetime import date
import time

def browserLogin():
    # This is needed if executing file from outside of project root directory
    dir = os.path.dirname(__file__)

    # Use the SELENIUM_URL environment variable to connect to the Selenium container
    selenium_url = os.getenv("SELENIUM_URL", "http://selenium-chrome:4444/wd/hub")

    # Set Chrome options to run in headless mode
    chrome_options = Options()
    if os.getenv("HEADLESS", "true").lower() != "false":
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    # Retry mechanism to wait for the Selenium server to be ready
    for _ in range(10):  # Retry up to 10 times
        try:
            driver = webdriver.Remote(
                command_executor=selenium_url,
                options=chrome_options
            )
            break  # If successful, exit the loop
        except Exception as e:
            print("Selenium server is not ready yet. Retrying in 2 seconds...")
            time.sleep(2)
    else:
        raise Exception("Failed to connect to Selenium server after multiple attempts.")

    try:
        # Requesting website
        driver.get("https://pickmypostcode.com/")
        print(f"Page title after loading: {driver.title}")
        wait = WebDriverWait(driver, 20)
        print("Waiting for the element to be present...")
        
        # First, wait for the presence of the element
        wait.until(EC.presence_of_element_located((By.XPATH, "/html/body/div[1]/div[1]/div/div/div[4]/div[2]/div/nav/button")))
        print("Element is present.")
        
        # Now, wait for it to be clickable
        wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[1]/div/div/div[4]/div[2]/div/nav/button")))
        print("Element found and clickable.")


        # Sign in
        print('Signing in')
        driver.find_element(By.XPATH, "/html/body/div[1]/div[1]/div/div/div[4]/div[2]/div/nav/button").click()

        # Scope all lookups to the sign-in modal's form so we never hit the hidden mobile/desktop duplicate
        modal_form = "//form[.//h3[normalize-space()='Sign into your account']]"
        postcode_input = wait.until(EC.element_to_be_clickable((By.XPATH, f"{modal_form}//input[@id='postcode']")))
        postcode_input.send_keys(os.environ.get("YOUR_POSTCODE"))
        driver.find_element(By.XPATH, f"{modal_form}//input[@id='email']").send_keys(os.environ.get("PMP_EMAIL"))
        driver.find_element(By.XPATH, f"{modal_form}//button[@type='submit']").click()
    
        # Load other draw pages to claim bonus
        print("Requesting Video Draw Page")
        driver.get("https://pickmypostcode.com/video/")
        time.sleep(1)

        print("Requesting Survey Draw Page")
        driver.get("https://pickmypostcode.com/survey-draw/")
        time.sleep(0.5)

        print("Requesting Stackpot Draw Page")
        driver.get("https://pickmypostcode.com/stackpot/")
        time.sleep(0.5)

        print("Requesting Bonus Draw Draw Page")
        driver.get("https://pickmypostcode.com/your-bonus/")
        time.sleep(0.5)
        driver.close()

    except Exception as e:
        print(f"An error occurred: {e}")
        driver.save_screenshot(f'{dir}/logs/error_screenshot.png')
        raise e

    finally:
        # Close the browser
        print('Closing browser')
        driver.quit()

    # Update database with the current date of login
    with open(f'{dir}/logs/pastData.json') as f:
        pastData = json.load(f)
        pastData['lastBrowserLogin'] = str(date.today())

    with open(f'{dir}/logs/pastData.json', 'w') as f:
        json.dump(pastData, f, indent=2)

if __name__ == "__main__":
    browserLogin()
