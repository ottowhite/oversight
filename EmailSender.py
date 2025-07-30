import yagmail
import smtplib
from dotenv import load_dotenv
import os

class EmailSender:
	def __init__(self, email):
		load_dotenv()
		self.email = email
		assert os.getenv("GMAIL_APP_PASSWORD") is not None, "GMAIL_APP_PASSWORD is not set"
		self.yag = yagmail.SMTP(email, os.getenv("GMAIL_APP_PASSWORD"))

	def send_email(self, to, subject, lines):
		try:
			self.yag.send(
				to=to,
				subject=subject,
				contents="\n\n".join(lines)
			)
		except smtplib.SMTPAuthenticationError as e:
			raise Exception(f"Incorrect gmail app password for {self.email}")
		except Exception as e:
			raise Exception(f"Error sending email to {to}: {e}")

	def __del__(self):
		self.yag.close()

if __name__ == "__main__":
	email_sender = EmailSender("otto.white.apps@gmail.com")
	email_sender.send_email(
		to="otto.white20@imperial.ac.uk",
		subject="Another email from Python",
		lines=[
			"This is the body of the email.",
			"You can also include HTML if you want."
		]
	)