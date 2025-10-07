"""
Test Email Monitor - Test email monitoring functionality
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.email_monitor import email_monitor
from config.worker_config import WorkerConfig


async def test_email_connection():
    """Test IMAP connection"""
    print("\n" + "=" * 60)
    print("📧 TESTING EMAIL MONITOR")
    print("=" * 60)
    
    # Print config
    print(f"\nIMAP Server: {WorkerConfig.EMAIL_IMAP_SERVER}:{WorkerConfig.EMAIL_IMAP_PORT}")
    print(f"Username: {WorkerConfig.EMAIL_USERNAME}")
    print(f"Password: {'*' * len(WorkerConfig.EMAIL_PASSWORD) if WorkerConfig.EMAIL_PASSWORD else 'NOT SET'}")
    
    # Test connection
    print("\n🔌 Testing IMAP connection...")
    mail = email_monitor.connect_to_imap()
    
    if mail:
        print("✅ Connection successful!")
        
        # Check inbox
        print("\n📬 Checking inbox...")
        try:
            status, messages = mail.search(None, 'ALL')
            if status == 'OK':
                count = len(messages[0].split())
                print(f"✅ Found {count} total messages in inbox")
                
                # Check unread
                status, unread = mail.search(None, 'UNSEEN')
                if status == 'OK':
                    unread_count = len(unread[0].split()) if unread[0] else 0
                    print(f"📭 Unread messages: {unread_count}")
            
            mail.logout()
            print("\n✅ Test completed successfully!")
            
        except Exception as e:
            print(f"❌ Error checking inbox: {e}")
    else:
        print("❌ Connection failed!")
        print("\nTroubleshooting:")
        print("1. Check EMAIL_USERNAME and EMAIL_PASSWORD in .env")
        print("2. If using Gmail, enable 'App Passwords' in Google Account settings")
        print("3. Make sure IMAP is enabled in your email settings")
    
    print("=" * 60 + "\n")


async def test_one_check():
    """Test one inbox check cycle"""
    print("\n" + "=" * 60)
    print("📧 TESTING ONE INBOX CHECK")
    print("=" * 60 + "\n")
    
    try:
        await email_monitor.check_inbox()
        print("\n✅ Inbox check completed")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60 + "\n")


async def main():
    """Main test function"""
    print("\nEmail Monitor Test Options:")
    print("1. Test connection")
    print("2. Test one inbox check")
    print("3. Run both tests")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        await test_email_connection()
    elif choice == '2':
        await test_one_check()
    elif choice == '3':
        await test_email_connection()
        await asyncio.sleep(2)
        await test_one_check()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())