"""
RAG Vector Store using ChromaDB
Handles document loading, embedding, and retrieval
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import os
from pathlib import Path

# Initialize ChromaDB
chroma_client = chromadb.PersistentClient(
    path="./chroma_db",
    settings=Settings(anonymized_telemetry=False)
)

# Initialize embedding model
embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Get or create collection
knowledge_collection = chroma_client.get_or_create_collection(
    name="company_knowledge",
    metadata={"description": "Company knowledge base for RAG"}
)


def add_document_to_knowledge_base(
    doc_id: str,
    text: str,
    metadata: Dict = None
) -> bool:
    """
    Add a document chunk to the knowledge base
    
    Args:
        doc_id: Unique document ID
        text: Text content to embed
        metadata: Additional metadata (source, category, etc.)
    """
    try:
        # Generate embedding
        embedding = embedding_model.encode(text).tolist()
        
        # Add to collection
        knowledge_collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}],
            ids=[doc_id]
        )
        return True
    except Exception as e:
        print(f"❌ Error adding document: {e}")
        return False


def query_knowledge_base(
    query: str,
    top_k: int = 3,
    relevance_threshold: float = 0.7
) -> List[Dict]:
    """
    Query the knowledge base for relevant documents
    
    Args:
        query: User's question
        top_k: Number of results to return
        relevance_threshold: Minimum similarity score (0-1)
    
    Returns:
        List of relevant documents with metadata
    """
    try:
        # Generate query embedding
        query_embedding = embedding_model.encode(query).tolist()
        
        # Search
        results = knowledge_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        documents = []
        if results['documents'] and len(results['documents'][0]) > 0:
            for i, doc in enumerate(results['documents'][0]):
                # ChromaDB returns distance, convert to similarity
                distance = results['distances'][0][i]
                similarity = 1 - distance  # Assuming cosine distance
                
                if similarity >= relevance_threshold:
                    documents.append({
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "similarity": similarity,
                        "id": results['ids'][0][i]
                    })
        
        return documents
    except Exception as e:
        print(f"❌ Error querying knowledge base: {e}")
        return []


def load_knowledge_from_directory(directory_path: str = "./knowledge_base"):
    """
    Load all documents from knowledge_base directory
    """
    from pypdf import PdfReader
    import json
    
    path = Path(directory_path)
    if not path.exists():
        print(f"⚠️ Knowledge base directory not found: {directory_path}")
        return
    
    doc_count = 0
    
    # Process each file
    for file_path in path.glob("**/*"):
        if file_path.is_file():
            print(f"📄 Processing: {file_path.name}")
            
            try:
                # PDF files
                if file_path.suffix.lower() == '.pdf':
                    reader = PdfReader(str(file_path))
                    for page_num, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text.strip():
                            doc_id = f"{file_path.stem}_page_{page_num}"
                            add_document_to_knowledge_base(
                                doc_id=doc_id,
                                text=text,
                                metadata={
                                    "source": file_path.name,
                                    "page": page_num,
                                    "type": "pdf"
                                }
                            )
                            doc_count += 1
                
                # Text/Markdown files
                elif file_path.suffix.lower() in ['.txt', '.md']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                        # Split into chunks if too large
                        chunks = chunk_text(text, max_tokens=500)
                        for i, chunk in enumerate(chunks):
                            doc_id = f"{file_path.stem}_chunk_{i}"
                            add_document_to_knowledge_base(
                                doc_id=doc_id,
                                text=chunk,
                                metadata={
                                    "source": file_path.name,
                                    "chunk": i,
                                    "type": file_path.suffix[1:]
                                }
                            )
                            doc_count += 1
                
                # JSON files
                elif file_path.suffix.lower() == '.json':
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Flatten JSON to text
                        text = json.dumps(data, indent=2)
                        doc_id = f"{file_path.stem}_json"
                        add_document_to_knowledge_base(
                            doc_id=doc_id,
                            text=text,
                            metadata={
                                "source": file_path.name,
                                "type": "json"
                            }
                        )
                        doc_count += 1
            
            except Exception as e:
                print(f"❌ Error processing {file_path.name}: {e}")
    
    print(f"✅ Loaded {doc_count} documents into knowledge base")


def chunk_text(text: str, max_tokens: int = 500) -> List[str]:
    """
    Split text into chunks of approximately max_tokens
    """
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        current_chunk.append(word)
        current_size += 1
        
        if current_size >= max_tokens:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_size = 0
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks


# Initialize on import
if __name__ == "__main__":
    print("🚀 Initializing RAG knowledge base...")
    load_knowledge_from_directory()
    print("✅ RAG system ready!")