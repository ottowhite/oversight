import asyncio
import aiohttp
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def send_twilio_sms(to: str, from_number: str, body: str) -> dict:
    """
    Send an SMS message using Twilio's API asynchronously.
    
    Args:
        to: The recipient's phone number (e.g., '+447557345060')
        from_number: The sender's phone number (e.g., '+447576018285')
        body: The message content
    
    Returns:
        dict: The JSON response from Twilio API
    
    Raises:
        aiohttp.ClientError: If there's an error with the HTTP request
        ValueError: If required environment variables are missing
    """
    # Get Twilio credentials from environment
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    if not account_sid:
        raise ValueError("TWILIO_ACCOUNT_SID environment variable is required")
    if not auth_token:
        raise ValueError("TWILIO_AUTH_TOKEN environment variable is required")
    
    # Twilio API endpoint
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    
    # Prepare form data
    data = {
        'To': to,
        'From': from_number,
        'Body': body
    }
    
    # Create basic auth header
    auth = aiohttp.BasicAuth(account_sid, auth_token)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, auth=auth) as response:
                response.raise_for_status()  # Raises an exception for HTTP error status codes
                return await response.json()
    
    except aiohttp.ClientError as e:
        print(f"Error sending SMS: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise


async def main():
    """Example usage of the send_twilio_sms function."""
    try:
        # Send the same message as in the original curl command
        result = await send_twilio_sms(
            to="+447462003706",
            from_number="+447576018285",
            body="Hows it going"
        )
        print("SMS sent successfully!")
        print(f"Message SID: {result.get('sid')}")
        print(f"Status: {result.get('status')}")
        
    except Exception as e:
        print(f"Failed to send SMS: {e}")


if __name__ == "__main__":
    asyncio.run(main())