import json
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent
ASSETS_DIR = ROOT_DIR / "assets"
MODELS_JSON = ASSETS_DIR / "models.json"
TOOLBOXES_JSON = ASSETS_DIR / "toolboxes.json"

def load_models() -> list[dict]:
    if MODELS_JSON.exists():
        with open(MODELS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def load_toolboxes() -> dict:
    if TOOLBOXES_JSON.exists():
        with open(TOOLBOXES_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_official_registry() -> str:
    return load_toolboxes().get("registry", "docker.io/kyuz0/amd-strix-halo-toolboxes")
