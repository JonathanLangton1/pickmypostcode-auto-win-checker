from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium import webdriver
from dotenv import load_dotenv
from datetime import date
import json
import os

load_dotenv()


def browserLogin():
    # This is needed if executing file from outside of project root directory
    dir = os.path.dirname(__file__)

    fireFoxOptions = webdriver.FirefoxOptions()
    fireFoxOptions.headless = True
    driver = webdriver.Firefox(options=fireFoxOptions)

    # Requesting website
    print('Requesting website')
    driver.get("https://pickmypostcode.com/")
    wait = WebDriverWait(driver, 20)
    wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[2]/div[2]/div[2]/nav/ul/li[5]/button[2]")))

    # Sign in
    print('Signing in')
    driver.find_element(By.XPATH, "/html/body/div[2]/div[2]/div[2]/nav/ul/li[5]/button[2]").click()
    driver.find_element(By.XPATH, '//*[@id="confirm-ticket"]').send_keys(os.environ.get("YOUR_POSTCODE"))
    driver.find_element(By.XPATH, '//*[@id="confirm-email"]').send_keys(os.environ.get("PMP_EMAIL"))
    driver.find_element(By.XPATH, '/html/body/div[2]/div[2]/div[2]/main/div[1]/section/div/div/div/form/button').click()
    driver.close()


    # Update database with current date of login
    with open(f'{dir}/pastData.json') as f:
        pastData = json.load(f)
        pastData['lastBrowserLogin'] = str(date.today())

    with open(f'{dir}/pastData.json', 'w') as f:
        json.dump(pastData, f, indent=2)