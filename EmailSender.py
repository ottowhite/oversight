import logging
import yagmail
import smtplib
from dotenv import load_dotenv
import os

# Cron example
# * * * * * python3 /home/ow20/code/open-router-test/EmailSender.py >> /home/ow20/code/open-router-test/logs/cron.log 2>&1

# Configure logging to actually print
logging.basicConfig(
    level=logging.INFO,
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(levelname)s] %(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class EmailSender:
	def __init__(self, email):
		load_dotenv()
		logger.info(f"Initialising email sender for {email}")

		self.email = email

		if os.getenv("GMAIL_APP_PASSWORD") is None:
			logger.error("GMAIL_APP_PASSWORD is not set")
			raise Exception("GMAIL_APP_PASSWORD is not set")

		self.yag = yagmail.SMTP(email, os.getenv("GMAIL_APP_PASSWORD"))

	def send_email(self, to, subject, contents):
		try:
			self.yag.send(
				to=to,
				subject=subject,
				contents=contents
			)
		except smtplib.SMTPAuthenticationError as e:
			logger.error(f"Incorrect gmail app password for {self.email}")
		except Exception as e:
			logger.error(f"Error sending email to {to}: {e}")
	
	def send_email_multiple_recipients(self, recipients, subject, contents):
		for recipient in recipients:
			self.send_email(recipient, subject, contents)
	
	def __del__(self):
		self.yag.close()

if __name__ == "__main__":
	email_sender = EmailSender("otto.white.apps@gmail.com")
	email_sender.send_email_multiple_recipients(
		recipients=["otto.white20@imperial.ac.uk", "whiteotto4@gmail.com"],
		subject="Another email from Python",
		contents="This is the body of the email. You can also include HTML if you want."
	)
