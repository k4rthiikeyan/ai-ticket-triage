"""Public RAG API; implementations are separated by responsibility."""
from .services.provider import OpenRouterGateway, OpenRouterError
from .services.retrieval import VectorStore, split_text, embed_query
from .services.triage import run_rag, run_rules, validate_generation, empty_result, PROMPT_VERSION
