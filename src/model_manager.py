import os
import re
import glob
import json
import fnmatch
from huggingface_hub import HfApi
from pathlib import Path
from src.config import read_user_config, write_user_config, logger

def get_models_dir() -> Path:
    conf = read_user_config()
    if "models_dir" in conf:
        try:
            return Path(os.path.expanduser(conf["models_dir"]))
        except Exception:
            logger.exception("Failed to resolve models directory path")
    return Path(os.path.expanduser("~/models"))

def save_models_dir(path_str: str) -> bool:
    conf = read_user_config()
    conf["models_dir"] = path_str
    if write_user_config(conf):
        try:
            new_dir = Path(os.path.expanduser(path_str))
            new_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            logger.exception("Failed to create models directory")
    return False

def get_active_platform() -> str:
    """Reads the active platform ID from config, defaults to 'strix-halo'."""
    conf = read_user_config()
    return conf.get("active_platform", "strix-halo")

def save_active_platform(platform_id: str) -> bool:
    """Persists the active platform ID to the config file."""
    conf = read_user_config()
    conf["active_platform"] = platform_id
    return write_user_config(conf)

def get_default_toolbox(platform_id: str) -> str | None:
    conf = read_user_config()
    defaults = conf.get("default_toolboxes", {})
    return defaults.get(platform_id)

def save_default_toolbox(platform_id: str, toolbox_name: str) -> bool:
    conf = read_user_config()
    defaults = conf.get("default_toolboxes", {})
    defaults[platform_id] = toolbox_name
    conf["default_toolboxes"] = defaults
    return write_user_config(conf)

def scan_local_models() -> list[dict]:
    models_dir = get_models_dir()
    if not models_dir.exists():
        return []
    
    found = set()
    for root, dirs, files in os.walk(models_dir):
        for f in files:
            if f.endswith(".gguf"):
                path = Path(root) / f
                rel_path = path.relative_to(models_dir)
                
                # Check for sharded models (-0000X-of-0000Y)
                if "-000" in f and "-of-000" in f:
                    grouped_pattern = re.sub(r"-000\d+-of-000\d+\.gguf$", "-*-of-*.gguf", str(rel_path))
                    found.add(grouped_pattern)
                else:
                    found.add(str(rel_path))
                    
    return [{"name": m, "path": str(models_dir / m)} for m in sorted(list(found))]

def is_quant_downloaded(repo: str, quant: str, walk_cache: list = None) -> bool:
    models_dir = get_models_dir()
    if not models_dir.exists():
        return False
        
    repo_base = repo.split('/')[-1].replace('-GGUF', '').lower()
    # Normalized form strips hyphens/underscores for flexible comparison
    repo_norm = repo_base.replace('-', '').replace('_', '')
    
    # 1. Exact path match based on standard download dir
    standard_dir = models_dir / repo.split('/')[-1]
    if (standard_dir / quant).exists():
        return True
    
    def _dir_matches_repo(dirpath: str) -> bool:
        """Check if a directory path is related to this specific repo."""
        rel = os.path.relpath(dirpath, models_dir).lower()
        for part in rel.split(os.sep):
            if part == '.':
                continue
            part_norm = part.replace('-', '').replace('_', '')
            # Require repo_base to be IN the dir name (not the reverse),
            # so "qwen3635ba3b" won't match a dir for "qwen3635ba3bmtp"
            if repo_norm in part_norm:
                return True
        return False
        
    # 2. Fuzzy scan across models_dir
    walk_data = walk_cache if walk_cache is not None else os.walk(models_dir)
    for root, dirs, files in walk_data:
        if quant.endswith(".gguf"):
            # Only match files in directories related to this repo
            if not _dir_matches_repo(root):
                continue
            if "*" in quant:
                for f in files:
                    if fnmatch.fnmatch(f, quant):
                        return True
            else:
                if quant in files:
                    return True
        else:
            # quant is a folder name like "BF16"
            if quant in dirs:
                if _dir_matches_repo(root):
                    return True
                try:
                    for f in os.listdir(os.path.join(root, quant)):
                        if repo_base in f.lower():
                            return True
                except OSError:
                    pass
                        
    return False

def resolve_model_path(pattern_path: str) -> str:
    """Resolves a pattern like *-of-*.gguf to the first actual file."""
    actual_files = glob.glob(pattern_path)
    if actual_files:
        actual_files.sort()
        return actual_files[0]
    return pattern_path

def get_hf_quants(repo: str) -> list[str]:
    api = HfApi()
    try:
        files = api.list_repo_files(repo_id=repo, repo_type="model")
    except Exception:
        logger.exception(f"Failed to list HF files for repo: {repo}")
        return []

    quants = set()
    for f in files:
        if f.endswith(".gguf"):
            parts = f.split('/')
            if len(parts) > 1:
                # It's in a subfolder (e.g., "BF16")
                quants.add(parts[0])
            else:
                # Top level file: Check if it's a shard
                if "-000" in f and "-of-000" in f:
                    grouped_pattern = re.sub(r"-000\d+-of-000\d+\.gguf$", "-*-of-*.gguf", f)
                    quants.add(grouped_pattern)
                else:
                    quants.add(f)
    return sorted(list(quants))

import sys

def get_download_cmd(repo: str, quant_pattern: str) -> list[str]:
    # Determine the pattern
    if quant_pattern.endswith(".gguf"):
        download_pattern = quant_pattern
    else:
        download_pattern = f"{quant_pattern}/*"
        
    final_dir = str(get_models_dir() / repo.split('/')[-1])
    
    # Use the hf executable from the current Python environment
    hf_bin = os.path.join(os.path.dirname(sys.executable), "hf")
    if not os.path.exists(hf_bin):
        hf_bin = "hf" # Fallback to PATH if not found
    
    cmd = [
        hf_bin, "download",
        repo,
        "--include", download_pattern,
        "--local-dir", final_dir
    ]
    return cmd
