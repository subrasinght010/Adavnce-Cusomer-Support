"""
Setup script to initialize RAG knowledge base
Run this once to load all documents
"""

import sys
sys.path.append('..')

from tools.vector_store import load_knowledge_from_directory
from pathlib import Path

def setup_rag_system():
    """Initialize the RAG knowledge base"""
    
    print("=" * 60)
    print("RAG KNOWLEDGE BASE SETUP")
    print("=" * 60)
    
    # Check if knowledge_base directory exists
    kb_path = Path("./knowledge_base")
    if not kb_path.exists():
        print(f"\n❌ Knowledge base directory not found: {kb_path}")
        print("Creating directory...")
        kb_path.mkdir(parents=True, exist_ok=True)
        
        # Create sample files
        print("Creating sample knowledge files...")
        
        # Sample FAQ
        with open(kb_path / "faqs.txt", "w") as f:
            f.write("""
                    # Frequently Asked Questions

                    Q: What is your refund policy?
                    A: We offer a 30-day money-back guarantee. If you're not satisfied, contact us within 30 days of purchase for a full refund.

                    Q: How long does shipping take?
                    A: Standard shipping takes 5-7 business days. Express shipping is available for 2-3 days delivery.

                    Q: What payment methods do you accept?
                    A: We accept all major credit cards, debit cards, UPI, net banking, and cash on delivery.

                    Q: Do you offer technical support?
                    A: Yes, we provide 24/7 technical support via phone, email, and chat.

                    Q: What are your business hours?
                    A: We're open Monday to Saturday, 9 AM to 6 PM IST. Sunday is closed.
                                """)
        
        # Sample pricing
        with open(kb_path / "pricing.txt", "w") as f:
            f.write("""
                    # Product Pricing

                    ## Basic Plan
                    - Price: ₹999/month
                    - Features: 10 users, 100GB storage, email support
                    - Best for: Small teams

                    ## Professional Plan
                    - Price: ₹2,999/month
                    - Features: 50 users, 500GB storage, priority support, analytics
                    - Best for: Growing businesses

                    ## Enterprise Plan
                    - Price: Custom pricing
                    - Features: Unlimited users, unlimited storage, dedicated account manager, 24/7 support
                    - Best for: Large organizations

                    All plans include:
                    - Free 14-day trial
                    - No credit card required
                    - Cancel anytime
                                """)
        
        print("✅ Sample files created")
    
    # Load documents
    print(f"\n📚 Loading documents from: {kb_path}")
    load_knowledge_from_directory(str(kb_path))
    
    print("\n" + "=" * 60)
    print("✅ RAG SYSTEM READY!")
    print("=" * 60)
    print("\nYou can now:")
    print("1. Add more documents to ./knowledge_base/")
    print("2. Run this script again to update the knowledge base")
    print("3. Start the FastAPI server to use RAG in production")


if __name__ == "__main__":
    setup_rag_system()