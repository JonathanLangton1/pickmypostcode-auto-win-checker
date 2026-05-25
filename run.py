from summariseWeeklyResults import summariseWeeklyResults
from checkResults import checkResults
from browserLogin import browserLogin
from datetime import datetime, date
from sendEmail import sendEmail
import json
import os
import sys
import traceback


def sendStartupTestEmail():
    """Send a one-shot confirmation email so the user can verify config is correct."""
    to = os.environ.get("NOTIFICATION_EMAIL_ADDRESS")
    subject = "Pick My Postcode auto checker is ready ✅"
    body = (
        "Hey 👋,\n\n"
        "Your Pick My Postcode auto win checker is set up correctly.\n"
        "It will run every day at 2pm and email you when your postcode wins "
        "(plus a summary every Sunday).\n\n"
        "Thanks,\nRobot"
    )
    html = f"<p>{body.replace(chr(10), '<br>')}</p>"
    ok = sendEmail(to, subject, body, html)
    if ok:
        print(f"Test email sent to {to}.")
    else:
        print("Failed to send test email — check EMAIL_ADDRESS / EMAIL_PASSWORD in .env")
        sys.exit(1)

def main():
    try:
        # This is needed if executing file from outside of project root directory
        script_dir = os.path.dirname(__file__)

        # If database file doesn't exist, create one
        if not os.path.isfile(f'{script_dir}/logs/pastData.json'):
            with open(f'{script_dir}/logs/pastData.json', 'w') as f:
                f.write("{}")

        # Sign in using Selenium
        browserLogin()

        # Get results
        results = checkResults(os.environ.get("YOUR_POSTCODE"))

        # If won, send email containing which draw you have won & a link to claim
        if results['hasWon']:
            winningDraws = [name for name, data in results['drawResults'].items() if data['hasWon']]
            print('Sending winning email')
            win_text = (
                f"Hey 👋,\n\nYou have won the following draw(s): {', '.join(winningDraws)}.\n"
                "Claim it here: https://pickmypostcode.com/\n\nThanks,\nRobot"
            )
            win_html = (
                f"<p>Hey 👋,</p><p>You have won the following draw(s): "
                f"<strong>{', '.join(winningDraws)}</strong>.</p>"
                f"<p>Claim it here: <a href=\"https://pickmypostcode.com/\">pickmypostcode.com</a></p>"
                f"<p>Thanks,<br>Robot</p>"
            )
            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'You have won the postcode lottery 🎉',
                win_text,
                win_html,
            )

        # If day is Sunday, send report of weekly data & also delete logs
        if date.today().weekday() == 6:
            summary = summariseWeeklyResults(os.environ.get("YOUR_POSTCODE"))
            print('Sending data summary')
            with open(f'{script_dir}/logs/pastData.json') as f:
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
            screenshot_path = f'{script_dir}/logs/error_screenshot.png'
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
    if "--test" in sys.argv:
        sendStartupTestEmail()
    else:
        main()
