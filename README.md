# Pickmypostcode Auto Win Checker

- Automates the login process to the Pick My Postcode website using Selenium.
- Checks lottery results based on the user's postcode set in `docker-compose.yml`.
- Sends email notifications for wins and weekly summaries.
- Runs on a daily schedule using Docker and Docker Compose (every day at 2pm)

## Requirements

- Docker
- Docker Compose

## Quick Start

* Clone this repo `git clone https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker`
* Navigate to the project directory `cd pickmypostcode-auto-win-checker`
* Set up environment variables listed in the `docker-compose.yml` file
* Build and run the application `docker-compose up --build`
* The checker will now automatically run every day at 2pm. If you wish to manually run it at any point for testing, you can do so by executing the following command: `docker exec pickmypostcode-checker python run.py`
