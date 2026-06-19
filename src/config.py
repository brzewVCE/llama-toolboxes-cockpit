import json
import os
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent
ASSETS_DIR = ROOT_DIR / "assets"
MODELS_JSON = ASSETS_DIR / "models.json"
TOOLBOXES_JSON = ASSETS_DIR / "toolboxes.json"

CONFIG_FILE = Path(os.path.expanduser("~/.llama-cockpit.conf"))

# Configure logging
_log_dir = Path(os.path.expanduser("~/.llama-cockpit"))
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "cockpit_debug.log"

logger = logging.getLogger("llama_cockpit")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(str(_log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def read_user_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load user config file")
        return {}

def write_user_config(conf: dict) -> bool:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(conf, f, indent=4)
        return True
    except Exception:
        logger.exception("Failed to write user config file")
        return False

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

def get_platforms() -> list[dict]:
    """Returns the list of platform definitions from toolboxes.json."""
    data = load_toolboxes()
    return data.get("platforms", [])

def get_platform(platform_id: str) -> dict | None:
    """Returns a single platform dict by its ID, or None if not found."""
    for p in get_platforms():
        if p.get("id") == platform_id:
            return p
    return None

def get_platform_registry(platform_id: str) -> str:
    """Returns the Docker registry for a given platform ID."""
    platform = get_platform(platform_id)
    if platform:
        return platform.get("registry", "")
    return ""


def get_model_config(selected_path: str) -> dict | None:
    """Look up a curated model entry by fuzzy-matching repo basename against a local file path."""
    if not selected_path:
        return None
    curated = load_models()
    path_lower = selected_path.lower()
    path_norm = path_lower.replace("-", "").replace("_", "")
    
    candidates = []
    for m in curated:
        repo_basename = m["repo"].split("/")[-1].lower()
        
        # 1. Exact repo_basename in path (e.g. folder name match)
        if repo_basename in path_lower:
            candidates.append((len(repo_basename), 3, m))
            continue
            
        # Clean suffix/infixes like -gguf, -gguf-mtp
        clean_basename = repo_basename
        if clean_basename.endswith("-gguf"):
            clean_basename = clean_basename[:-5]
        elif "-gguf-" in clean_basename:
            clean_basename = clean_basename.replace("-gguf-", "-")
            
        # 2. Cleaned basename in path
        if clean_basename in path_lower:
            candidates.append((len(clean_basename), 2, m))
            continue
            
        # 3. Normalized matching (ignoring hyphens and underscores)
        clean_norm = clean_basename.replace("-", "").replace("_", "")
        if clean_norm in path_norm:
            candidates.append((len(clean_norm), 1, m))
            
    if not candidates:
        return None
        
    # Sort candidates by:
    # - Strategy priority (3 = exact, 2 = clean, 1 = normalized) descending
    # - Match length descending (longer/more specific match wins)
    candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return candidates[0][2]



def get_inference_profiles(model_config: dict) -> dict:
    """Returns the inference_profiles dict for a model, or empty dict if none."""
    if not model_config:
        return {}
    return model_config.get("inference_profiles", {})


