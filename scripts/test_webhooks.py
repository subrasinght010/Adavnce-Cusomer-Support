"""
Test Webhooks - Test SMS and WhatsApp webhook handlers
"""

import sys
import os
import asyncio
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_sms_webhook(server_url: str = "http://localhost:8080"):
    """Test SMS webhook"""
    print("\n" + "=" * 60)
    print("📱 TESTING SMS WEBHOOK")
    print("=" * 60)
    
    # Simulate Twilio SMS webhook
    webhook_data = {
        'From': '+919876543210',
        'To': '+1234567890',
        'Body': 'Test message from SMS webhook test',
        'MessageSid': 'SM_TEST_12345'
    }
    
    print(f"\n📤 Sending test SMS webhook to: {server_url}/webhook/sms")
    print(f"Data: {webhook_data}")
    
    try:
        response = requests.post(
            f"{server_url}/webhook/sms",
            data=webhook_data,
            timeout=10
        )
        
        print(f"\n✅ Response status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        if response.status_code == 200:
            print("\n✅ SMS webhook test PASSED")
        else:
            print(f"\n❌ SMS webhook test FAILED: {response.status_code}")
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Connection failed. Is server running at {server_url}?")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("=" * 60 + "\n")


def test_whatsapp_webhook(server_url: str = "http://localhost:8080"):
    """Test WhatsApp webhook"""
    print("\n" + "=" * 60)
    print("💬 TESTING WHATSAPP WEBHOOK")
    print("=" * 60)
    
    # Simulate Twilio WhatsApp webhook
    webhook_data = {
        'From': 'whatsapp:+919876543210',
        'To': 'whatsapp:+1234567890',
        'Body': 'Test message from WhatsApp webhook test',
        'MessageSid': 'SM_TEST_WHATSAPP_12345',
        'NumMedia': '0'
    }
    
    print(f"\n📤 Sending test WhatsApp webhook to: {server_url}/webhook/whatsapp")
    print(f"Data: {webhook_data}")
    
    try:
        response = requests.post(
            f"{server_url}/webhook/whatsapp",
            data=webhook_data,
            timeout=10
        )
        
        print(f"\n✅ Response status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        if response.status_code == 200:
            print("\n✅ WhatsApp webhook test PASSED")
        else:
            print(f"\n❌ WhatsApp webhook test FAILED: {response.status_code}")
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Connection failed. Is server running at {server_url}?")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("=" * 60 + "\n")


def check_server_status(server_url: str = "http://localhost:8080"):
    """Check if server is running"""
    print(f"🔍 Checking server status at {server_url}...")
    
    try:
        response = requests.get(f"{server_url}/webhook/status", timeout=5)
        if response.status_code == 200:
            print("✅ Server is online")
            return True
        else:
            print("⚠️ Server responded but with unexpected status")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Server is not running at {server_url}")
        print("Start server with: python main.py")
        return False
    except Exception as e:
        print(f"❌ Error checking server: {e}")
        return False


def main():
    """Main test function"""
    print("\n" + "=" * 60)
    print("🧪 WEBHOOK TESTING UTILITY")
    print("=" * 60)
    
    server_url = input("\nEnter server URL (default: http://localhost:8080): ").strip()
    if not server_url:
        server_url = "http://localhost:8080"
    
    # Check server status
    if not check_server_status(server_url):
        return
    
    print("\nTest Options:")
    print("1. Test SMS webhook")
    print("2. Test WhatsApp webhook")
    print("3. Test both")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        test_sms_webhook(server_url)
    elif choice == '2':
        test_whatsapp_webhook(server_url)
    elif choice == '3':
        test_sms_webhook(server_url)
        test_whatsapp_webhook(server_url)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()