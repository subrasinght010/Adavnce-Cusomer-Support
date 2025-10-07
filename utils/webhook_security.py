"""
Webhook Security - Verify webhook signatures and prevent abuse
"""

import hmac
import hashlib
import os
from typing import Dict
from fastapi import Request, HTTPException
from twilio.request_validator import RequestValidator


class WebhookSecurity:
    def __init__(self):
        self.twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.validator = RequestValidator(self.twilio_auth_token) if self.twilio_auth_token else None
    
    async def verify_twilio_signature(self, request: Request) -> bool:
        """
        Verify Twilio webhook signature
        
        Args:
            request: FastAPI request object
        
        Returns:
            True if signature is valid
        
        Raises:
            HTTPException if signature is invalid
        """
        if not self.validator:
            print("⚠️ Twilio auth token not configured, skipping signature verification")
            return True
        
        try:
            # Get signature from header
            signature = request.headers.get('X-Twilio-Signature', '')
            
            if not signature:
                print("⚠️ No Twilio signature found in headers")
                raise HTTPException(status_code=403, detail="Missing signature")
            
            # Get URL
            url = str(request.url)
            
            # Get form data
            form_data = await request.form()
            params = dict(form_data)
            
            # Validate signature
            is_valid = self.validator.validate(url, params, signature)
            
            if not is_valid:
                print("❌ Invalid Twilio signature")
                raise HTTPException(status_code=403, detail="Invalid signature")
            
            print("✅ Twilio signature verified")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"❌ Error verifying signature: {e}")
            raise HTTPException(status_code=500, detail="Signature verification failed")
    
    def verify_custom_signature(self, payload: str, signature: str, secret: str) -> bool:
        """
        Verify custom webhook signature (for non-Twilio webhooks)
        
        Args:
            payload: Request payload
            signature: Signature from header
            secret: Shared secret
        
        Returns:
            True if signature is valid
        """
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    async def verify_sendgrid_signature(self, request: Request) -> bool:
        """
        Verify SendGrid webhook signature (for email webhooks)
        
        Returns:
            True if signature is valid
        """
        sendgrid_secret = os.getenv('SENDGRID_WEBHOOK_SECRET')
        
        if not sendgrid_secret:
            return True  # Skip verification if not configured
        
        signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature', '')
        timestamp = request.headers.get('X-Twilio-Email-Event-Webhook-Timestamp', '')
        
        body = await request.body()
        payload = timestamp + body.decode('utf-8')
        
        return self.verify_custom_signature(payload, signature, sendgrid_secret)


# Singleton instance
webhook_security = WebhookSecurity()