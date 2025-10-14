# test/test_inbound_workflow.py
"""
Comprehensive Inbound Workflow Tests - Multi-Intent Support
Tests all scenarios including multi-intent and entity extraction
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
from prompts.robust_system_prompts import VALID_INTENTS


class TestInboundWorkflow:
    """Test all inbound scenarios with DB verification"""
    
    def __init__(self):
        self.test_results = []
    
    async def run_all_tests(self):
        """Execute all test cases"""
        
        print("=" * 80)
        print("COMPREHENSIVE INBOUND WORKFLOW TESTS - MULTI-INTENT SUPPORT")
        print("=" * 80)
        
        test_cases = [
            self.test_simple_greeting,
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
            self.test_multiple_intents_single_message,
            self.test_entity_accumulation,
        ]
        
        for test in test_cases:
            try:
                print(f"\n{'='*80}")
                await test()
            except Exception as e:
                print(f"❌ {test.__name__} FAILED: {e}")
                import traceback
                traceback.print_exc()
                self.test_results.append((test.__name__, False, str(e)))
        
        self._print_summary()
    
    async def _run_test(
        self,
        test_name: str,
        lead_phone: str,
        messages: list,
        expected_intent: str = None,
        expected_intents: list = None,
        expected_actions: list = None,
        expected_entities: dict = None,
        check_db: bool = True
    ):
        """Run single test case with multi-intent support"""
        
        print(f"\nTEST: {test_name}")
        print(f"{'-'*80}")
        
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
        
        # Build conversation history from DB
        conversation_history = []
        for conv in existing_convs:
            conversation_history.append({
                "role": "user" if conv.sender == "user" else "assistant",
                "content": conv.message,
                "timestamp": conv.timestamp.isoformat()
            })
        
        # Track messages sent in THIS test
        expected_messages = []
        
        # Process each message
        for i, msg in enumerate(messages, 1):
            print(f"\n[Turn {i}] User: {msg}")
            expected_messages.append({"role": "user", "content": msg})
            
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
            intents = intelligence.get("intents", [intelligence.get("intent")])
            actions = intelligence.get("next_actions", [])
            entities = intelligence.get("entities", {})
            
            print(f"[Turn {i}] AI: {response}")
            print(f"         Intents: {intents}")
            print(f"         Confidence: {intelligence.get('intent_confidence', 0):.2f}")
            print(f"         Actions: {actions}")
            print(f"         Entities: {entities}")
            
            # Update conversation history
            expected_messages.append({"role": "assistant", "content": response})
            conversation_history.append({"role": "user", "content": msg, "timestamp": datetime.utcnow().isoformat()})
            conversation_history.append({"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()})
        
        # Validate final result
        intelligence = result.get("intelligence_output", {})
        
        # Check intents (support both single and multiple)
        actual_intents = intelligence.get("intents", [])
        if not actual_intents:
            actual_intents = [intelligence.get("intent", "general_inquiry")]
        
        # Validate expected intents
        if expected_intents:
            if set(actual_intents) != set(expected_intents):
                print(f"❌ Intent mismatch!")
                print(f"   Expected: {expected_intents}")
                print(f"   Got: {actual_intents}")
                self.test_results.append((test_name, False, f"Intent mismatch: expected {expected_intents}, got {actual_intents}"))
                return
        elif expected_intent:
            if expected_intent not in actual_intents:
                print(f"❌ Intent mismatch!")
                print(f"   Expected: {expected_intent}")
                print(f"   Got: {actual_intents}")
                self.test_results.append((test_name, False, f"Intent mismatch: expected {expected_intent}, got {actual_intents}"))
                return
        
        # Validate actions
        actual_actions = intelligence.get("next_actions", [])
        if expected_actions is not None:
            if set(actual_actions) != set(expected_actions):
                print(f"❌ Actions mismatch!")
                print(f"   Expected: {expected_actions}")
                print(f"   Got: {actual_actions}")
                self.test_results.append((test_name, False, f"Actions mismatch: expected {expected_actions}, got {actual_actions}"))
                return
        
        # Validate entities (if specified)
        if expected_entities:
            actual_entities = intelligence.get("entities", {})
            for key, expected_value in expected_entities.items():
                if key not in actual_entities:
                    print(f"❌ Missing entity: {key}")
                    self.test_results.append((test_name, False, f"Missing entity: {key}"))
                    return
                # Note: We don't check exact value as LLM might format differently
        
        # DB verification
        if check_db:
            db_valid = await self._verify_db(lead_id, messages_before, expected_messages)
            if not db_valid:
                self.test_results.append((test_name, False, "DB verification failed"))
                return
        
        print(f"\n✅ {test_name} PASSED")
        self.test_results.append((test_name, True, None))
    
    async def _verify_db(self, lead_id: int, messages_before: int, expected_messages: list) -> bool:
        """Verify messages saved to database"""
        try:
            async with AsyncSessionLocal() as db:
                db_manager = DBManager(db)
                conversations = await db_manager.get_conversations_by_lead(lead_id, limit=100)
                
                new_messages = conversations[messages_before:]
                actual_count = len(new_messages)
                expected_count = len(expected_messages)
                
                print(f"\n📊 DB Verification: {actual_count}/{expected_count} messages saved")
                
                if actual_count != expected_count:
                    print(f"⚠️  Message count mismatch")
                    return False
                
                print("✓ DB verification passed")
                return True
        except Exception as e:
            print(f"❌ DB verification error: {e}")
            return False
    
    # ========================================================================
    # TEST CASES
    # ========================================================================
    
    async def test_simple_greeting(self):
        """Test: Simple greeting"""
        await self._run_test(
            test_name="Simple Greeting",
            lead_phone="+11234567890",
            messages=["Hey there!"],
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
        """Test: Schedule callback with time"""
        await self._run_test(
            test_name="Callback Scheduling",
            lead_phone="+11234567892",
            messages=[
                "I need to speak with someone",
                "Can you call me tomorrow at 2 PM?"
            ],
            expected_intent="callback_request",
            expected_actions=["schedule_callback"],
            expected_entities={"callback_time": "2 PM"}
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
            expected_actions=["send_email"],
            expected_entities={"email": "test@example.com"}
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
            expected_actions=["send_sms"]
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
            expected_actions=["send_whatsapp"]
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
            expected_intents=["send_details_email", "callback_request"],
            expected_actions=["send_email", "schedule_callback"],
            expected_entities={"email": "enterprise@test.com", "callback_time": "Friday at 10 AM"}
        )
    
    async def test_unclear_request(self):
        """Test: Unclear/ambiguous request"""
        await self._run_test(
            test_name="Unclear Request",
            lead_phone="+11234567800",
            messages=["I need help with that thing"],
            expected_intent="general_inquiry"
        )
    
    async def test_multiple_intents_single_message(self):
        """Test: Multiple intents in one message"""
        await self._run_test(
            test_name="Multiple Intents - Single Message",
            lead_phone="+11234567801",
            messages=[
                "Send me pricing via email at multi@test.com and also schedule a callback for tomorrow at 3 PM"
            ],
            expected_intents=["send_details_email", "callback_request"],
            expected_actions=["send_email", "schedule_callback"],
            expected_entities={
                "email": "multi@test.com",
                "callback_time": "3 PM",
                "content_type": "pricing"
            }
        )
    
    async def test_entity_accumulation(self):
        """Test: Entity accumulation across turns"""
        await self._run_test(
            test_name="Entity Accumulation",
            lead_phone="+11234567802",
            messages=[
                "Can you send me details?",
                "Pricing information",
                "Via email",
                "john.doe@example.com"
            ],
            expected_intent="send_details_email",
            expected_actions=["send_email"],
            expected_entities={
                "email": "john.doe@example.com",
                "content_type": "pricing",
                "channel": "email"
            }
        )
    
    async def test_callback_without_time(self):
        """Test: Callback request without time (should ask for clarification)"""
        await self._run_test(
            test_name="Callback Without Time",
            lead_phone="+11234567803",
            messages=["I want a callback"],
            expected_intent="callback_request",
            expected_actions=[],  # No action without time
        )
    
    async def test_email_without_address(self):
        """Test: Email request without address (should ask for clarification)"""
        await self._run_test(
            test_name="Email Without Address",
            lead_phone="+11234567804",
            messages=["Email me the pricing"],
            expected_intent="send_details_email",
            expected_actions=[],  # No action without email
        )
    
    async def test_whatsapp_and_email_combo(self):
        """Test: Request info via multiple channels"""
        await self._run_test(
            test_name="WhatsApp and Email Combo",
            lead_phone="+11234567805",
            messages=[
                "Send me the catalog on WhatsApp and email the pricing to info@company.com"
            ],
            expected_intents=["send_details_whatsapp", "send_details_email"],
            expected_actions=["send_whatsapp", "send_email"],
            expected_entities={
                "email": "info@company.com"
            }
        )
    
    async def test_complex_multi_action(self):
        """Test: Complex request with 3+ actions"""
        await self._run_test(
            test_name="Complex Multi-Action",
            lead_phone="+11234567806",
            messages=[
                "I have a complaint about my order, send me your refund policy via email at complaint@test.com, and have someone call me today at 5 PM"
            ],
            expected_intents=["complaint", "send_details_email", "callback_request"],
            expected_actions=["escalate_to_human", "send_email", "schedule_callback"],
            expected_entities={
                "email": "complaint@test.com",
                "callback_time": "5 PM"
            }
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
        else:
            print("\n🎉 ALL TESTS PASSED!")
        
        print("\n" + "=" * 80)
        
        # Print valid intents for reference
        print("\n📋 VALID INTENTS:")
        for intent in VALID_INTENTS:
            print(f"  - {intent}")
        
        print("\n" + "=" * 80)


async def main():
    """Run all tests"""
    tester = TestInboundWorkflow()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())