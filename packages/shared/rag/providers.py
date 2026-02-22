from typing import List
from packages.shared.rag.interfaces import EmbeddingProvider
import os

class FastEmbedProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        # Import lazily to avoid heavy init if not used
        from fastembed import TextEmbedding
        
        self._model_name = model_name
        self._dim = 384 # BGE-small-en-v1.5 dimension
        
        # We can configure cache_dir if needed to persist across docker restarts
        cache_dir = os.environ.get("FASTEMBED_CACHE_DIR", "/app/data/models")
        os.makedirs(cache_dir, exist_ok=True)
        
        self.model = TextEmbedding(model_name=self._model_name, cache_dir=cache_dir)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # fastembed returns a generator of numpy arrays
        embeddings_gen = self.model.embed(texts)
        return [list(emb) for emb in embeddings_gen]

# Optional OpenAIProvider could go here if OPENAI_API_KEY is present
class OpenAIProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "text-embedding-3-small"):
        import openai
        self._model_name = model_name
        self._dim = 1536
        self.client = openai.OpenAI() # expects OPENAI_API_KEY envar
        
    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            input=texts,
            model=self._model_name
        )
        return [item.embedding for item in response.data]

def get_embedding_provider() -> EmbeddingProvider:
    # Defaulting to fastembed for local/docker ease without keys
    provider_type = os.environ.get("EMBEDDING_PROVIDER", "fastembed")
    if provider_type == "openai":
        return OpenAIProvider()
    return FastEmbedProvider()
