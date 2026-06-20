import hashlib
import requests
from urllib.parse import urljoin
from typing import Dict, List, Any, Optional
from openai import OpenAI
from .config import settings
from .logger import get_logger

logger = get_logger("vector_store")


def get_hash_vector(text: str, dims: int = 1536) -> List[float]:
    """
    Convert a string into a deterministic pseudo-random normalized vector.
    Serves as a reliable fallback when OpenAI is not available.
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vector = []
    for i in range(dims):
        byte_idx = i % len(h)
        value = h[byte_idx] / 255.0
        variation = ((i * 7 + h[(i + 1) % len(h)]) % 256) / 512.0
        vector.append((value + variation) / 2.0)
    mag = sum(x * x for x in vector) ** 0.5
    if mag > 0:
        vector = [x / mag for x in vector]
    return vector


def get_openai_embeddings(
    texts: List[str], api_key: str, model: str = "text-embedding-3-small"
) -> Optional[List[List[float]]]:
    """
    Attempts to fetch embeddings from OpenAI.
    """
    if not api_key or not api_key.startswith("sk-") or len(api_key) < 20:
        return None
    try:
        client = OpenAI(api_key=api_key)
        truncated = [t[:10000] for t in texts]
        resp = client.embeddings.create(input=truncated, model=model)
        return [item.embedding for item in resp.data]
    except Exception as e:
        logger.warning(
            f"OpenAI embedding generation failed, falling back to hashes. Error: {str(e)}"
        )
        return None


def embed_texts(texts: List[str], dims: int = 1536) -> List[List[float]]:
    """
    Embeds texts using OpenAI if available, else falls back to hash vectors.
    """
    if not texts:
        return []
    openai_res = get_openai_embeddings(texts, settings.OPENAI_API_KEY)
    if openai_res and len(openai_res) == len(texts):
        return openai_res
    return [get_hash_vector(t, dims) for t in texts]


class QdrantVectorStore:
    """
    Unified Qdrant Vector Store interface.
    """

    def __init__(self) -> None:
        self.host = settings.QDRANT_HOST
        self.port = settings.QDRANT_PORT
        self.base_url = f"http://{self.host}:{self.port}"
        try:
            resp = requests.get(urljoin(self.base_url, "/collections"), timeout=3)
            if resp.status_code == 200:
                logger.info(
                    "Successfully connected to Qdrant Vector Store",
                    extra={"url": self.base_url},
                )
            else:
                logger.error(
                    "Qdrant returned non-200 status code.",
                    extra={"status": resp.status_code},
                )
                raise Exception(f"Qdrant connection failed: {resp.status_code}")
        except Exception as e:
            logger.error(
                "Could not connect to Qdrant.",
                extra={"error": str(e), "url": self.base_url},
            )
            raise e

    def reset_store(self) -> None:
        """Clears all collections and points."""
        try:
            resp = requests.get(urljoin(self.base_url, "/collections"), timeout=5)
            if resp.status_code == 200:
                collections = resp.json().get("result", {}).get("collections", [])
                for col in collections:
                    name = col.get("name")
                    if name:
                        requests.delete(
                            urljoin(self.base_url, f"/collections/{name}"), timeout=5
                        )
            logger.info("Qdrant Vector Store successfully reset.")
        except Exception as e:
            logger.error("Failed to reset Qdrant", extra={"error": str(e)})

    def _create_collection_if_needed(self, name: str, vector_size: int = 1536) -> None:
        try:
            url = urljoin(self.base_url, f"/collections/{name}")
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                return
            body = {"vectors": {"size": vector_size, "distance": "Cosine"}}
            resp = requests.put(url, json=body, timeout=5)
            if resp.status_code in (200, 409):
                logger.info(f"Created Qdrant collection: {name}")
            else:
                logger.warning(
                    f"Unexpected response creating collection: {resp.status_code}"
                )
        except Exception as e:
            logger.error(f"Error creating collection {name}: {str(e)}")

    def upsert_points(
        self,
        collection: str,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        """
        Upserts a batch of vectors and payloads to Qdrant.
        """
        if not vectors:
            return
        vector_size = len(vectors[0])
        self._create_collection_if_needed(collection, vector_size)
        try:
            points = []
            for pid, vec, payload in zip(ids, vectors, payloads):
                numeric_id = abs(hash(pid)) % (2**63)
                points.append(
                    {
                        "id": numeric_id,
                        "vector": vec,
                        "payload": {**payload, "_original_str_id": pid},
                    }
                )
            url = urljoin(self.base_url, f"/collections/{collection}/points?wait=true")
            resp = requests.put(url, json={"points": points}, timeout=15)
            if resp.status_code == 200:
                logger.info(
                    f"Successfully indexed {len(points)} points in Qdrant collection '{collection}'"
                )
            else:
                logger.error(
                    f"Failed to upsert to Qdrant: {resp.status_code}. Content: {resp.text}"
                )
        except Exception as e:
            logger.error(f"Failed to write to Qdrant: {str(e)}.")

    def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 5,
        filter_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Searches the vector store using cosine similarity and returns a list of matching payloads.
        Supports filtering by specific original string IDs.
        """
        try:
            url = urljoin(self.base_url, f"/collections/{collection}/points/search")
            body = {"vector": query_vector, "limit": top_k, "with_payload": True}
            if filter_ids:
                body["filter"] = {
                    "must": [{"key": "_original_str_id", "match": {"any": filter_ids}}]
                }
            resp = requests.post(url, json=body, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("result", []):
                    payload = item.get("payload", {})
                    orig_id = payload.pop("_original_str_id", str(item.get("id")))
                    results.append(
                        {
                            "id": orig_id,
                            "score": item.get("score", 0.0),
                            "payload": payload,
                        }
                    )
                return results
            else:
                logger.error(f"Search failed in Qdrant: {resp.status_code}.")
                return []
        except Exception as e:
            logger.error(f"Failed to query Qdrant: {str(e)}.")
            return []

    def scroll(
        self,
        collection: str,
        filter_must: List[Dict[str, Any]],
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves points from the specified Qdrant collection based on payload matching criteria,
        without performing similarity search.
        """
        try:
            url = urljoin(self.base_url, f"/collections/{collection}/points/scroll")
            body = {
                "filter": {"must": filter_must},
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            }
            resp = requests.post(url, json=body, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("result", {}).get("points", []):
                    payload = item.get("payload", {})
                    orig_id = payload.pop("_original_str_id", str(item.get("id")))
                    results.append(
                        {
                            "id": orig_id,
                            "payload": payload,
                        }
                    )
                return results
            else:
                logger.error(
                    f"Scroll failed in Qdrant: {resp.status_code}. Content: {resp.text}"
                )
                return []
        except Exception as e:
            logger.error(f"Failed to scroll Qdrant: {str(e)}.")
            return []


vector_db = QdrantVectorStore()

