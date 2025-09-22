"""
Simple test for the send_twilio_sms function.
This test validates the function structure without making actual API calls.
"""
import asyncio
import sys
import os

# Add the current directory to the path so we can import text
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from text import send_twilio_sms


async def test_function_structure():
    """Test that the function can be imported and has the right signature."""
    print("Testing function structure...")
    
    # Test that the function exists and is callable
    assert callable(send_twilio_sms), "send_twilio_sms should be callable"
    
    # Test that it's an async function
    import inspect
    assert inspect.iscoroutinefunction(send_twilio_sms), "send_twilio_sms should be async"
    
    print("✅ Function structure test passed!")
    
    # Test error handling for missing environment variables
    original_token = os.environ.get("TWILIO_AUTH_TOKEN")
    original_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    
    try:
        # Test missing account SID
        if "TWILIO_ACCOUNT_SID" in os.environ:
            del os.environ["TWILIO_ACCOUNT_SID"]
        if "TWILIO_AUTH_TOKEN" in os.environ:
            del os.environ["TWILIO_AUTH_TOKEN"]
        
        # This should raise a ValueError for missing account SID
        try:
            await send_twilio_sms("+1234567890", "+0987654321", "Test")
            assert False, "Should have raised ValueError for missing account SID"
        except ValueError as e:
            assert "TWILIO_ACCOUNT_SID environment variable is required" in str(e)
            print("✅ Account SID validation test passed!")
        
        # Test missing auth token (when account SID is present)
        os.environ["TWILIO_ACCOUNT_SID"] = "test_account_sid"
        
        try:
            await send_twilio_sms("+1234567890", "+0987654321", "Test")
            assert False, "Should have raised ValueError for missing auth token"
        except ValueError as e:
            assert "TWILIO_AUTH_TOKEN environment variable is required" in str(e)
            print("✅ Auth token validation test passed!")
        
    finally:
        # Restore the original environment variables if they existed
        if original_token:
            os.environ["TWILIO_AUTH_TOKEN"] = original_token
        if original_sid:
            os.environ["TWILIO_ACCOUNT_SID"] = original_sid


if __name__ == "__main__":
    asyncio.run(test_function_structure())
    print("\n🎉 All tests passed! The async function is working correctly.")
