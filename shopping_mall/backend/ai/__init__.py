"""AI module for FarmOS shopping mall."""
import os

# ChromaDB persistent data directory (relative to this file)
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_data")
