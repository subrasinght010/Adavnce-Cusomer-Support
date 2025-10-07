"""
Test script for RAG system
"""

import sys
sys.path.append('..')

from tools.vector_store import query_knowledge_base

def test_rag_queries():
    """Test RAG with sample queries"""
    
    test_queries = [
        "What is your refund policy?",
        "How much does the professional plan cost?",
        "Do you offer technical support?",
        "What are your business hours?",
        "Tell me about shipping options"
    ]
    
    print("=" * 60)
    print("RAG SYSTEM TEST")
    print("=" * 60)
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        print("-" * 60)
        
        results = query_knowledge_base(query, top_k=2, relevance_threshold=0.5)
        
        if results:
            for i, doc in enumerate(results, 1):
                print(f"\n{i}. Similarity: {doc['similarity']:.3f}")
                print(f"   Source: {doc['metadata'].get('source', 'Unknown')}")
                print(f"   Content: {doc['content'][:200]}...")
        else:
            print("   ❌ No relevant documents found")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_rag_queries()