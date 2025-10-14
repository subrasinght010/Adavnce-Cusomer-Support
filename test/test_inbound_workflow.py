"""
Comprehensive Inbound Workflow Tests - All scenarios with DB validation
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from state.workflow_state import create_initial_state
from graph_workflows.workflow import workflow_router
from database.db import AsyncSessionLocal
from database.crud import DBManager


class TestInboundWorkflow:
    """Test all inbound scenarios with DB verification"""
    
    def __init__(self):
        self.test_results = []
    
    async def run_all_tests(self):
        """Execute all test cases"""
        
        print("=" * 80)
        print("COMPREHENSIVE INBOUND WORKFLOW TESTS")
        print("=" * 80)
        
        test_cases = [
            self.test_simple_query,
            self.test_pricing_request,
            self.test_callback_scheduling,
            self.test_send_email_details,
            self.test_send_sms_details,
            self.test_send_whatsapp_details,
            self.test_policy_query,
            self.test_product_query,
            self.test_complaint_escalation,
            self.test_multi_step_conversation,
            self.test_unclear_request,
            self.test_multiple_intents,
        ]
        
        for test in test_cases:
            # import ipdb; ipdb.set_trace()
            try:
                await test()
            except Exception as e:
                print(f"❌ {test.__name__} FAILED: {e}")
                self.test_results.append((test.__name__, False, str(e)))
        
        self._print_summary()
    
    async def _run_test(
        self,
        test_name: str,
        lead_phone: str,
        messages: list,
        expected_intent: str = None,
        expected_actions: list = None,
        check_db: bool = True
    ):
        """Run single test case"""
        
        print(f"\n{'=' * 80}")
        print(f"TEST: {test_name}")
        print(f"{'=' * 80}")
        
        # Create or get lead
        async with AsyncSessionLocal() as db:
            db_manager = DBManager(db)
            lead = await db_manager.get_or_create_lead(
                phone=lead_phone,
                name=f"Test User {lead_phone[-4:]}"
            )
            lead_id = lead.id
            
            # Count existing messages BEFORE test
            existing_convs = await db_manager.get_conversations_by_lead(lead_id, limit=100)
            messages_before = len(existing_convs)
        
        # Build in-memory conversation history from DB
        conversation_history = []
        for conv in existing_convs:
            conversation_history.append({
                "role": "user" if conv.sender == "user" else "assistant",
                "content": conv.message,
                "timestamp": conv.timestamp.isoformat()
            })
        
        # Track messages sent in THIS test
        messages_sent = []
        
        # Process each message in conversation
        for i, msg in enumerate(messages, 1):
            print(f"\n[Turn {i}] User: {msg}")
            messages_sent.append({"role": "user", "content": msg})
            
            state = create_initial_state(
                lead_id=str(lead_id),
                message=msg,
                channel="sms",
                direction="inbound",
                lead_data={
                    "phone": lead_phone,
                    "name": lead.name
                }
            )
            state["conversation_history"] = conversation_history
            
            # Run workflow
            result = await workflow_router.run(state)
            
            intelligence = result.get("intelligence_output", {})
            response = intelligence.get("response_text", "")
            intent = intelligence.get("intent")
            actions = intelligence.get("next_actions", [])
            
            print(f"[Turn {i}] AI: {response}")
            print(f"         Intent: {intent} (confidence: {intelligence.get('intent_confidence', 0):.2f})")
            print(f"         Actions: {actions}")
            
            messages_sent.append({"role": "ai", "content": response})
            
            # Update in-memory history
            conversation_history.append({
                "role": "user",
                "content": msg,
                "timestamp": datetime.now().isoformat()
            })
            conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat()
            })
            
            # Validate last message
            if i == len(messages):
                success = True
                
                if expected_intent and intent != expected_intent:
                    print(f"⚠️  Expected intent: {expected_intent}, got: {intent}")
                    success = False
                
                if expected_actions:
                    missing = set(expected_actions) - set(actions)
                    if missing:
                        print(f"⚠️  Missing actions: {missing}")
                        success = False
                
                # Verify DB save - pass what we actually sent
                if check_db:
                    db_check = await self._verify_db_dynamic(
                        lead_id, 
                        messages_before,
                        messages_sent
                    )
                    if not db_check:
                        print("⚠️  DB verification failed")
                        success = False
                
                status = "✅ PASSED" if success else "❌ FAILED"
                print(f"\n{status}")
                self.test_results.append((test_name, success, response))
                return success

    async def _verify_db_dynamic(self, lead_id: int, messages_before: int, expected_messages: list):
        """Verify DB matches what we actually sent"""
        # import ipdb; ipdb.set_trace()
        async with AsyncSessionLocal() as db:
            db_manager = DBManager(db)
            
            conversations = await db_manager.get_conversations_by_lead(lead_id, limit=100)
            print(f"Total messages in DB for lead {lead_id}: {len(conversations)} (before test: {messages_before})")
            
            # Get only NEW messages from this test
            new_messages = conversations[messages_before:]
            actual_count = len(new_messages)
            expected_count = len(expected_messages)
            # for i in new_messages:
            #     print(f"  DB Msg: sender={i.sender}, message={i.message}")
            
            # for j in expected_messages:
            #     print(f"  Expected Msg: role={j['role']}, content={j['content']}")
            
            print(f"\n📊 DB Check: {actual_count}/{expected_count} messages saved")
            
            if actual_count != expected_count:
                print(f"⚠️  Count mismatch")
                return False
            
            
            # Verify each message matches what we sent
            for i, (expected, actual) in enumerate(zip(expected_messages, new_messages)):
                print(f"expected: {expected} actual: sender={actual.sender}, message={actual.message}")
                expected_role = "user" if expected["role"] == "user" else "ai"
                

                if actual.sender != expected_role:
                    return False
                
                if actual.message != expected["content"]:
                    print(f"⚠️  Message {i+1}: content mismatch")
                    return False
            
            print("✓ DB verification passed")
            return True
        
    # ========================================================================
    # TEST CASES
    # ========================================================================
    
    async def test_simple_query(self):
        """Test: Simple greeting"""
        await self._run_test(
            test_name="Simple Greeting",
            lead_phone="+11234567890",
            messages=[" Hey there!"],
            expected_intent="greeting",
            expected_actions=[]
        )
    
    async def test_pricing_request(self):
        """Test: Pricing information request"""
        await self._run_test(
            test_name="Pricing Request",
            lead_phone="+11234567891",
            messages=["What are your pricing plans?"],
            expected_intent="pricing_query",
            expected_actions=[]
        )
    
    async def test_callback_scheduling(self):
        """Test: Schedule callback"""
        await self._run_test(
            test_name="Callback Scheduling",
            lead_phone="+11234567892",
            messages=[
                "I need to speak with someone",
                "Can you call me tomorrow at 2 PM?"
            ],
            expected_intent="callback_request",
            expected_actions=["schedule_callback"]
        )
    
    async def test_send_email_details(self):
        """Test: Send pricing via email"""
        await self._run_test(
            test_name="Email Details - Pricing",
            lead_phone="+11234567893",
            messages=[
                "I want pricing information",
                "Send it to my email: test@example.com"
            ],
            expected_intent="send_details_email",
            expected_actions=[]  # Pending send queued
        )
    
    async def test_send_sms_details(self):
        """Test: Send product info via SMS"""
        await self._run_test(
            test_name="SMS Details - Product",
            lead_phone="+11234567894",
            messages=[
                "Tell me about your products",
                "Text me the details"
            ],
            expected_intent="send_details_sms",
            expected_actions=[]
        )
    
    async def test_send_whatsapp_details(self):
        """Test: Send catalog via WhatsApp"""
        await self._run_test(
            test_name="WhatsApp Details - Catalog",
            lead_phone="+11234567895",
            messages=[
                "I need your full catalog",
                "WhatsApp it to me"
            ],
            expected_intent="send_details_whatsapp",
            expected_actions=[]
        )
    
    async def test_policy_query(self):
        """Test: Policy information request"""
        await self._run_test(
            test_name="Policy Query - Refund",
            lead_phone="+11234567896",
            messages=["What's your refund policy?"],
            expected_intent="policy_query",
            expected_actions=[]
        )
    
    async def test_product_query(self):
        """Test: Product features inquiry"""
        await self._run_test(
            test_name="Product Query - Features",
            lead_phone="+11234567897",
            messages=["What features does your product have?"],
            expected_intent="product_query",
            expected_actions=[]
        )
    
    async def test_complaint_escalation(self):
        """Test: Complaint handling"""
        await self._run_test(
            test_name="Complaint Escalation",
            lead_phone="+11234567898",
            messages=[
                "I have a problem with my order",
                "This is unacceptable, I want to speak to a manager"
            ],
            expected_intent="complaint",
            expected_actions=["escalate_to_human"]
        )
    
    async def test_multi_step_conversation(self):
        """Test: Complex multi-turn conversation"""
        await self._run_test(
            test_name="Multi-Step Conversation",
            lead_phone="+11234567899",
            messages=[
                "Hi, I'm interested in your services",
                "What's the pricing for enterprise?",
                "Can you email me the details? my email is enterprise@test.com",
                "Also schedule a call for Friday at 10 AM"
            ],
            expected_actions=["schedule_callback"]
        )
    
    async def test_unclear_request(self):
        """Test: Unclear/ambiguous request"""
        await self._run_test(
            test_name="Unclear Request",
            lead_phone="+11234567800",
            messages=["I need help with that thing"],
            expected_intent="general_inquiry"
        )
    
    async def test_multiple_intents(self):
        """Test: Multiple intents in one message"""
        await self._run_test(
            test_name="Multiple Intents",
            lead_phone="+11234567801",
            messages=[
                "Send me pricing via email at multi@test.com and also schedule a callback for tomorrow at 3 PM"
            ],
            expected_actions=["schedule_callback"]
        )
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    
    def _print_summary(self):
        """Print test results summary"""
        
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        total = len(self.test_results)
        passed = sum(1 for _, success, _ in self.test_results if success)
        failed = total - passed
        
        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for name, success, error in self.test_results:
                if not success:
                    print(f"  - {name}: {error}")
        
        print("\n" + "=" * 80)


async def main():
    """Run all tests"""
    tester = TestInboundWorkflow()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())