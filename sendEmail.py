import smtplib
from email.message import EmailMessage
import os


def sendEmail(to, subject, message, html_message):
    try:
        email_address = os.environ.get("EMAIL_ADDRESS")
        email_password = os.environ.get("EMAIL_PASSWORD")

        if email_address is None or email_password is None:
            # no email address or password
            # something is not configured properly
            print("Did you set email address and password correctly?")
            return False

        # create email
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f'Postcode Lottery Bot <{email_address}>'
        msg['To'] = to
        msg.set_content(message)
        msg.add_alternative(html_message, subtype='html')

        # send email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
            smtp.login(email_address, email_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print("Problem during send email")
        print(str(e))
    return False