# # """
# # Test script for Inbound Intelligence Agent
# # """

# # import asyncio
# # import sys
# # from pathlib import Path

# # # Add project root to path
# # sys.path.insert(0, str(Path(__file__).parent))

# # from nodes.inbound_intelligence_agent import inbound_intelligence_agent
# # from state.workflow_state import OptimizedWorkflowState


# # async def test_agent():
# #     """Test inbound agent with sample queries"""
    
# #     test_cases = [
# #         {
# #             "name": "Product Query",
# #             "state": {
# #                 "current_message": "What are your pricing plans?",
# #                 "lead_id": "test_001",
# #                 "lead_data": {"name": "John Doe"},
# #                 "channel": "web",
# #                 "conversation_history": [],
# #                 "llm_calls_made": 0
# #             }
# #         },
# #         {
# #             "name": "Callback Request",
# #             "state": {
# #                 "current_message": "Can you call me back tomorrow at 2 PM?",
# #                 "lead_id": "test_002",
# #                 "lead_data": {"name": "Jane Smith"},
# #                 "channel": "phone",
# #                 "conversation_history": [],
# #                 "llm_calls_made": 0
# #             }
# #         },
# #         {
# #             "name": "Send Details via Email",
# #             "state": {
# #                 "current_message": "Send me the product catalog on my email",
# #                 "lead_id": "test_003",
# #                 "lead_data": {"name": "Bob Wilson"},
# #                 "channel": "web",
# #                 "conversation_history": [],
# #                 "llm_calls_made": 0
# #             }
# #         },
# #         {
# #             "name": "WhatsApp Request",
# #             "state": {
# #                 "current_message": "Send pricing details on WhatsApp",
# #                 "lead_id": "test_004",
# #                 "lead_data": {"name": "Alice Brown"},
# #                 "channel": "phone",
# #                 "conversation_history": [],
# #                 "llm_calls_made": 0
# #             }
# #         }
# #     ]
    
# #     print("=" * 70)
# #     print("TESTING INBOUND INTELLIGENCE AGENT")
# #     print("=" * 70)
    
# #     for i, test in enumerate(test_cases, 1):
# #         print(f"\n{'─' * 70}")
# #         print(f"TEST {i}: {test['name']}")
# #         print(f"{'─' * 70}")
# #         print(f"Input: {test['state']['current_message']}")
# #         print(f"Lead: {test['state']['lead_data']['name']} ({test['state']['lead_id']})")
        
# #         try:
# #             result = await inbound_intelligence_agent.execute(test['state'])
            
# #             intelligence = result.get('intelligence_output', {})
            
# #             print(f"\n✅ SUCCESS")
# #             print(f"Intent: {intelligence.get('intent')}")
# #             print(f"Confidence: {intelligence.get('intent_confidence')}")
# #             print(f"Sentiment: {intelligence.get('sentiment')}")
# #             print(f"Urgency: {intelligence.get('urgency')}")
# #             print(f"Response: {intelligence.get('response_text')}")
# #             print(f"Needs Human: {intelligence.get('requires_human')}")
            
# #         except Exception as e:
# #             print(f"\n❌ FAILED: {e}")
    
# #     print(f"\n{'=' * 70}")
# #     print("TESTS COMPLETE")
# #     print("=" * 70)


# # async def test_tools_only():
# #     """Test individual tools"""
    
# #     print("\n" + "=" * 70)
# #     print("TESTING INDIVIDUAL TOOLS")
# #     print("=" * 70)
    
# #     agent = inbound_intelligence_agent
    
# #     # Test KB search
# #     print("\n1. Knowledge Base Search")
# #     result = agent._search_kb("pricing plans")
# #     print(f"Result: {result[:200]}...")
    
# #     # Test history
# #     print("\n2. Lead History")
# #     result = agent._get_history_sync("test_001")
# #     print(f"Result: {result}")
    
# #     # Test ticket check
# #     print("\n3. Ticket Status")
# #     result = agent._check_ticket("TKT-12345")
# #     print(f"Result: {result}")
    
# #     # Test escalation
# #     print("\n4. Create Escalation")
# #     result = agent._create_escalation("Customer needs immediate assistance")
# #     print(f"Result: {result}")


# # if __name__ == "__main__":
# #     print("\nStarting tests...\n")
    
# #     # Test full agent
# #     asyncio.run(test_agent())
    
# #     # Test tools individually
# #     asyncio.run(test_tools_only())
    
# #     print("\n✅ All tests completed!")



# """
# Test advanced multi-turn conversation scenarios
# """

# import asyncio
# import sys
# from pathlib import Path

# sys.path.insert(0, str(Path(__file__).parent))

# from nodes.inbound_intelligence_agent import inbound_intelligence_agent


# async def test_scenario(name: str, turns: list, lead_data: dict):
#     """Test a conversation scenario"""
#     print(f"\n{'=' * 70}")
#     print(f"SCENARIO: {name}")
#     print("=" * 70)
    
#     state = {
#         "lead_id": f"test_{name.lower().replace(' ', '_')}",
#         "lead_data": lead_data,
#         "channel": "phone",
#         "conversation_history": [],
#         "llm_calls_made": 0
#     }
    
#     for i, message in enumerate(turns, 1):
#         print(f"\n[Turn {i}] User: {message}")
#         state["current_message"] = message
        
#         try:
#             result = await inbound_intelligence_agent.execute(state)
#             state = result
#             intelligence = state.get('intelligence_output', {})
            
#             print(f"[Turn {i}] Agent: {intelligence.get('response_text')}")
#             if intelligence.get('entities'):
#                 print(f"         Entities: {intelligence.get('entities')}")
#             if intelligence.get('next_actions'):
#                 print(f"         Actions: {intelligence.get('next_actions')}")
#         except Exception as e:
#             print(f"❌ Error: {e}")
#             break


# async def run_all_scenarios():
#     """Run multiple conversation scenarios"""
    
#     scenarios = [
#         {
#             "name": "Pricing Inquiry with Follow-up",
#             "lead_data": {"name": "John Smith", "email": "john@example.com"},
#             "turns": [
#                 "Hi, what are your pricing plans?",
#                 "Do you offer discounts for annual plans?",
#                 "Can you send the pricing sheet to my email?",
#                 "Also add information about enterprise features"
#             ]
#         },
#         {
#             "name": "Support Escalation",
#             "lead_data": {"name": "Mary Johnson", "phone": "+919876543210"},
#             "turns": [
#                 "I'm having issues with my account",
#                 "It's not loading properly since yesterday",
#                 "I already tried clearing cache",
#                 "This is urgent, can someone call me back today at 5 PM?"
#             ]
#         },
#         {
#             "name": "Channel Switching",
#             "lead_data": {"name": "Robert Lee", "email": "robert@example.com", "phone": "+919123456789"},
#             "turns": [
#                 "Tell me about your product features",
#                 "Send the details on WhatsApp",
#                 "Wait, use email instead",
#                 "And also schedule a demo call for next Monday at 2 PM"
#             ]
#         },
#         {
#             "name": "Complex Multi-Request",
#             "lead_data": {"name": "Lisa Wong", "email": "lisa@example.com"},
#             "turns": [
#                 "I need information about your services",
#                 "What's the difference between standard and premium?",
#                 "Send me the comparison on email and call me tomorrow",
#                 "Make it 10 AM tomorrow",
#                 "Also send your product catalog on WhatsApp"
#             ]
#         },
#         {
#             "name": "Clarification Loop",
#             "lead_data": {"name": "David Brown", "phone": "+919988776655"},
#             "turns": [
#                 "I want to know about pricing",
#                 "The cloud storage plans",
#                 "For 5 users",
#                 "Send it to my email please",
#                 "david.brown@company.com"
#             ]
#         }
#     ]
    
#     for scenario in scenarios:
#         await test_scenario(
#             scenario["name"],
#             scenario["turns"],
#             scenario["lead_data"]
#         )
#         await asyncio.sleep(1)  # Brief pause between scenarios


# if __name__ == "__main__":
#     print("🧪 ADVANCED MULTI-TURN CONVERSATION TESTING")
#     asyncio.run(run_all_scenarios())
#     print("\n✅ All scenarios completed!")


"""Simple test for robust prompts"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from nodes.inbound_agent_v2 import inbound_agent as inbound_intelligence_agent

async def test():
    state = {
        "lead_id": "001",
        "lead_data": {"name": "John", "email": "john@test.com"},
        "channel": "phone",
        "conversation_history": [],
        "llm_calls_made": 0
    }
    
    messages = [
        "What's your pricing?",
        "Send it to my email",
        "Also call me tomorrow",
        'at 6 PM'
    ]
    
    for i, msg in enumerate(messages, 1):
        print(f"\n[{i}] User: {msg}")
        state["current_message"] = msg
        state = await inbound_intelligence_agent.execute(state)
        
        intel = state["intelligence_output"]
        print(f"[{i}] Agent: {intel['response_text']}")
        print(f"    Intent: {intel['intent']}")
        print(f"    Entities: {intel.get('entities', {})}")
        print(f"    Actions: {intel.get('next_actions', [])}")

asyncio.run(test())