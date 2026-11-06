"""项目路径和默认参数；导入配置不要求同时提供所有厂商密钥。"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
PARSED = Path(os.getenv("RAG_PARSED_DIR", str(ROOT / "data/parsed")))
DB_PATH = Path(os.getenv("RAG_DB_PATH", str(ROOT / "data/chroma")))
COLLECTION_NAME = "byd_reports"

# 修改切块或向量模型后必须另建匹配索引，不能继续复用旧向量。
CHUNK_SIZE, OVERLAP = 512, 64
EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
RERANK_URL = "https://api.siliconflow.cn/v1/rerank"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

CHAT_PROVIDERS = {
    "siliconflow": ("https://api.siliconflow.cn/v1/chat/completions", "Qwen/Qwen3.5-4B", "SILICONFLOW_API_KEY"),
    "deepseek": ("https://api.deepseek.com/chat/completions", "deepseek-flash", "DeepSeek_API_KEY"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4.7-flash", "GLM_API_KEY"),
}
CHAT_PROVIDER = os.getenv("RAG_CHAT_PROVIDER", "siliconflow")
if CHAT_PROVIDER not in CHAT_PROVIDERS:
    raise ValueError("RAG_CHAT_PROVIDER 必须是 siliconflow、deepseek 或 glm")
_url, _model, CHAT_KEY_ENV = CHAT_PROVIDERS[CHAT_PROVIDER]
CHAT_URL = os.getenv("RAG_CHAT_URL", _url)
CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", _model)
TRUST_ENV = os.getenv("RAG_TRUST_ENV", "false").lower() in {"1", "true", "yes"}

K_RRF = 60
CANDIDATE_N = 20
TOP_K = 5
MAX_CONTEXT_CHARS = 8000
CONTEXT_RADIUS = 2
