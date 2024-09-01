from summariseWeeklyResults import summariseWeeklyResults
from checkResults import checkResults
from browserLogin import browserLogin
from datetime import datetime, date
from sendEmail import sendEmail
import json
import os
import traceback

def main():
    try:
        # This is needed if executing file from outside of project root directory
        dir = os.path.dirname(__file__)

        # If database file doesn't exist, create one
        if not os.path.isfile(f'{dir}/logs/pastData.json'):
            with open(f'{dir}/logs/pastData.json', 'w') as f:
                f.write("{}")

        # Sign in using Selenium
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
            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'You have won the postcode lottery 🎉',
                f'Hey 👋,\n\nYou have won the following draw(s): {winningDraws}.\nClaim it here: https://pickmypostcode.com/\n\nThanks,\nRobot'
            )

        # If day is Sunday, send report of weekly data & also delete logs
        if date.today().weekday() == 6:
            summary = summariseWeeklyResults(os.environ.get("YOUR_POSTCODE"))
            print('Sending data summary')
            with open(f'{dir}/logs/pastData.json') as f:
                weeklyData = json.load(f)
            
            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'Weekly postcode lottery data summary 📊',
                f'Hey 👋,\n\n {weeklyData} \n\nThanks,\nRobot',
                summary
            )

    except Exception as e:
        # Capture the traceback to include in the error email
        error_message = traceback.format_exc()
        print("An error occurred: ", error_message)

        # Attempt to send an error notification email
        try:
            screenshot_path = 'error_screenshot.png'
            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'Script Error Notification 🚨',
                f'Hey 👋,\n\nAn error occurred while running the script:\n\n{error_message}\n\nPlease check the logs for more details.\n\nThanks,\nRobot',
                f'<p>Hey 👋,<br><br>An error occurred while running the script:<br><pre>{error_message}</pre><br>Please check the attached screenshot for more details.<br><br>Thanks,<br>Robot</p>',
                attachment_path=screenshot_path if os.path.exists(screenshot_path) else None
            )
            
            # Delete the screenshot after sending the email
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
                print("Deleted screenshot after sending the email.")
            
        except Exception as email_error:
            # If sending the email fails, log the email error
            print("Failed to send error notification email: ", email_error)

if __name__ == '__main__':
    main()
