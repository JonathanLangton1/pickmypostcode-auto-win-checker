# Pickmypostcode Auto Win Checker

## Project Setup

* Clone this repo
* Create virtual environment (recommended)
* Install requirements `pip install -r requirements.txt`
* Create `.env` file and enter info (use [env.example](env.example) for reference)
* Set up the following CRON job: `0 14 * * * path/to/venv/python path/to/run.py`


## Project Flow
1. Sign in using Selenium ([here's why](https://pickmypostcode.com/rules/#:~:text=We%20may%20temporarily%20remove%20entries%20that%20have%20not%20visited%20the%20site%20for%20over%20a%20week.)) each day & visit draw pages to claim bonuses.
2. Check if user has won by requesting results directly from their API
3. If user has won, send email detailing which draw(s) have been won
4. If user hasn't won, if it is a Sunday, send summary email with data, otherwise do nothing