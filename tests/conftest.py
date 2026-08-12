import os
from pathlib import Path

Path(".local").mkdir(exist_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test.db")
os.environ.setdefault("AUTO_SEED", "false")
