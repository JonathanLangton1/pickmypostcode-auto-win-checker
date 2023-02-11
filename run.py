from checkResults import checkResults
from browserLogin import browserLogin
from datetime import datetime, date
from sendEmail import sendEmail
from dotenv import load_dotenv
import json
import os


load_dotenv()

def main():

    # If database file doesn't exist, create one
    if os.path.isfile('pastData.json') == False:
        with open("pastData.json", "w") as f:
            f.write("{}")

    # If user hasn't logged in for past 6 days, then log in using Selenium
    with open('pastData.json') as f:
        pastData = json.load(f)
        if 'lastBrowserLogin' in pastData.keys():
            lastBrowserLogin = datetime.strptime(pastData['lastBrowserLogin'], '%Y-%m-%d').date()
            delta = date.today() - lastBrowserLogin
            if delta.days >= 6:
                browserLogin()
        else:
            browserLogin()



    # Get results
    results = checkResults(os.environ.get("YOUR_POSTCODE"))


    # If won, send email containing which draw you have won & a link to claim
    if results['hasWon']:
        winningDraws = []
        for drawName, data in results['drawResults'].items():
            if data['hasWon']:
                print('Sending winning email')
                winningDraws.append(drawName)
        sendEmail(os.environ.get("NOTIFICATION_EMAIL_ADDRESS"), 'You have won the postcode lottery 🎉', f'Hey 👋,\n\nYou have won the following draw(s): {winningDraws}.\nClaim it here: https://pickmypostcode.com/\n\nThanks,\nRobot')


    # If day is Sunday, send report of weekly data & also delete logs
    if date.today().weekday() == 6:
        print('Sending data summary')
        with open('pastData.json') as f:
            weeklyData = json.load(f)
        f.close()
        sendEmail(os.environ.get("NOTIFICATION_EMAIL_ADDRESS"), 'Weekly postcode lottery data summary 📊', f'Hey 👋,\n\n {weeklyData} \n\nThanks,\nRobot')

    

if __name__ == '__main__':
    main()