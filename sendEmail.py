import smtplib
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email import encoders
import os
import mimetypes


def sendEmail(to, subject, message, html_message, attachment_path=None):
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
        msg['From'] = email_address
        msg['To'] = to
        msg.set_content(message)
        msg.add_alternative(html_message, subtype='html')

        # Attach the file if it exists
        if attachment_path and os.path.isfile(attachment_path):
            with open(attachment_path, 'rb') as f:
                file_data = f.read()
                file_name = os.path.basename(attachment_path)
                mime_type, _ = mimetypes.guess_type(attachment_path)
                mime_type, mime_subtype = mime_type.split('/', 1)
                msg.add_attachment(file_data, maintype=mime_type, subtype=mime_subtype, filename=file_name)

        # send email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_address, email_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print("Problem during send email")
        print(str(e))
    return False