# Download the helper library from https://www.twilio.com/docs/python/install
import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(account_sid, auth_token)
otto = "+447462003706"
charlie = "+447557345060"

message = client.messages.create(
    from_="whatsapp:+14155238886",
    body="Hey charlie! Otto here, I'm calling to schedule a lunch meeting. Could you let me know your availability?",
    to=f"whatsapp:{charlie}",
)

print(message.body)