import os
import json
import hashlib
from typing import Dict, Any

try:
    from sentence_transformers import SentenceTransformer
except Exception as exc:
    SentenceTransformer = None  # type: ignore

MODEL_NAME = os.environ.get("EMBED_MODEL", "paraphrase-MiniLM-L6-v2")

class EmbeddingManager:
    """Maintain embeddings for text files in a directory."""

    def __init__(self, root_dir: str) -> None:
        self.root_dir = os.path.abspath(root_dir)
        self.index_path = os.path.join(self.root_dir, "embeddings.json")
        self.model = None
        if SentenceTransformer:
            try:
                self.model = SentenceTransformer(MODEL_NAME)
            except Exception:
                self.model = None
        self.index: Dict[str, Dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as fh:
                    self.index = json.load(fh)
            except (OSError, json.JSONDecodeError):
                self.index = {}

    def _save_index(self) -> None:
        try:
            with open(self.index_path, "w", encoding="utf-8") as fh:
                json.dump(self.index, fh)
        except OSError:
            pass

    def update_file(self, rel_path: str) -> None:
        """Update embedding for a file if changed."""
        if not self.model:
            return
        full_path = os.path.abspath(os.path.join(self.root_dir, rel_path))
        if not full_path.startswith(self.root_dir):
            return
        if not os.path.isfile(full_path):
            return
        try:
            with open(full_path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        info = self.index.get(rel_path)
        if info and info.get("hash") == digest:
            return
        vector = self.model.encode([text])[0].tolist()
        self.index[rel_path] = {"hash": digest, "vector": vector}
        self._save_index()
