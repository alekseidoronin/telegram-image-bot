import logging
import httpx
import numpy as np
import database
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

EMBED_MODEL = "models/gemini-embedding-2-preview"

async def get_embedding(text: str):
    """
    Fetches embedding for the given text using Gemini API.
    Returns bytes (numpy float32 array).
    """
    if not text or not text.strip():
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/{EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}"
    
    payload = {
        "model": EMBED_MODEL,
        "content": {
            "parts": [{"text": text}]
        },
        "output_dimensionality": 768  # Optimizing for space vs quality
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            embedding_values = data.get("embedding", {}).get("values", [])
            if not embedding_values:
                return None
                
            # Convert to numpy array float32 and then to bytes for DB storage
            vec = np.array(embedding_values, dtype=np.float32)
            return vec.tobytes()
            
    except Exception as e:
        logger.error(f"Error getting embedding: {e}")
        return None

async def get_multi_embeddings(texts: list):
    """
    Batch embedding retrieval (optional optimization).
    """
    # Placeholder for batch if needed
    pass
