import os
import json
import re
from pathlib import Path

CONFIG_FILE = Path(os.path.expanduser("~/.llama-cockpit.conf"))

def get_configs_dir() -> Path:
    """Gets the path to the custom configs directory, defaulting to ~/.llama-cockpit/configs."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                conf = json.load(f)
                if "configs_dir" in conf:
                    path = Path(os.path.expanduser(conf["configs_dir"]))
                    path.mkdir(parents=True, exist_ok=True)
                    return path
        except Exception:
            pass
            
    default_path = Path(os.path.expanduser("~/.llama-cockpit/configs"))
    default_path.mkdir(parents=True, exist_ok=True)
    return default_path

def save_configs_dir(path_str: str) -> bool:
    """Saves the path to the custom configs directory in ~/.llama-cockpit.conf."""
    conf = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                conf = json.load(f)
        except Exception:
            pass
            
    conf["configs_dir"] = path_str
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(conf, f, indent=4)
        new_dir = Path(os.path.expanduser(path_str))
        new_dir.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def load_built_in_configs() -> list[dict]:
    """Loads default configurations bundled in assets/configs.json."""
    assets_dir = Path(__file__).parent / "assets"
    built_in_file = assets_dir / "configs.json"
    if built_in_file.exists():
        try:
            with open(built_in_file, "r", encoding="utf-8") as f:
                configs = json.load(f)
                for cfg in configs:
                    cfg["is_custom"] = False
                    cfg["filename"] = ""
                return configs
        except Exception:
            pass
    return []

def scan_local_configs() -> list[dict]:
    """Scans the configs directory for all *.json files and parses them."""
    configs_dir = get_configs_dir()
    if not configs_dir.exists():
        return []
        
    configs = []
    for f_name in os.listdir(configs_dir):
        if f_name.endswith(".json"):
            f_path = configs_dir / f_name
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if isinstance(cfg, dict) and "name" in cfg:
                        cfg["is_custom"] = True
                        cfg["filename"] = f_name
                        if "models" not in cfg:
                            cfg["models"] = []
                        configs.append(cfg)
            except Exception:
                pass
    return sorted(configs, key=lambda x: x["name"].lower())

def get_all_configs() -> list[dict]:
    """Returns a merged list of built-in and custom user configs (user configs shadow built-ins with same name)."""
    built_in = load_built_in_configs()
    custom = scan_local_configs()
    
    merged = {}
    # Load built-ins first
    for cfg in built_in:
        merged[cfg["name"]] = cfg
        
    # Custom configs overwrite/shadow built-ins with the same name
    for cfg in custom:
        merged[cfg["name"]] = cfg
        
    return sorted(list(merged.values()), key=lambda x: x["name"].lower())

def save_custom_config(name: str, commands: str, models: list[str]) -> bool:
    """Saves/creates a custom config in the user's configs directory."""
    configs_dir = get_configs_dir()
    # Sanitize name to generate a safe filename
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    filename = f"{safe_name}.json"
    f_path = configs_dir / filename
    
    data = {
        "name": name,
        "args": commands,
        "models": models
    }
    
    try:
        with open(f_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config file: {e}")
        return False

def delete_custom_config_file(filename: str) -> bool:
    """Deletes a custom config file from the configs directory."""
    if not filename:
        return False
    configs_dir = get_configs_dir()
    f_path = configs_dir / filename
    if f_path.exists():
        try:
            os.remove(f_path)
            return True
        except Exception:
            pass
    return False
