"""StudySoft configuration."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# On Vercel the filesystem is read-only except /tmp
_ON_VERCEL = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
_RUNTIME_ROOT = Path("/tmp/studysoft") if _ON_VERCEL else ROOT

MATERIALS_DIR = _RUNTIME_ROOT / "materials"
DATA_DIR = _RUNTIME_ROOT / "data"
INDEX_PATH = DATA_DIR / "materials_index.pkl"

# Seed course files shipped in the repo (copied into /tmp on Vercel)
REPO_MATERIALS_DIR = ROOT / "materials"

# Audio
SAMPLE_RATE = 16000
CHUNK_SECONDS = 4.0  # how often we transcribe a slice
OVERLAP_SECONDS = 0.5

# Whisper
WHISPER_MODEL = "base"  # tiny | base | small | medium
WHISPER_DEVICE = "cpu"  # "cuda" if you have an NVIDIA GPU
WHISPER_COMPUTE = "int8"

# Q&A
MIN_QUESTION_CHARS = 12
TOP_K_CHUNKS = 4
CHUNK_SIZE = 450
CHUNK_OVERLAP = 60

# Overlay
OVERLAY_WIDTH = 420
OVERLAY_HEIGHT = 520
OVERLAY_OPACITY = 0.92
