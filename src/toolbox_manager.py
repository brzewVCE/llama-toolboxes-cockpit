import subprocess
import os
import urllib.request
import json
import shutil
import functools
from src.config import logger

# Podman workaround marker for containers with missing/corrupted creation time
PODMAN_NO_DATE_MARKER = "292 years ago"

def detect_engines() -> list[str]:
    engines = []
    if shutil.which("podman"):
        engines.append("podman")
    if shutil.which("docker"):
        engines.append("docker")
    return engines

@functools.lru_cache(maxsize=1)
def _is_ubuntu_debian_arch() -> bool:
    """Check if the OS is Ubuntu, Debian, or Arch Linux."""
    if not os.path.exists("/etc/os-release"):
        return False
    try:
        with open("/etc/os-release", "r") as f:
            content = f.read().lower()
        return any(dist in content for dist in ("id=ubuntu", "id=debian", "id=arch"))
    except Exception:
        logger.exception("Failed to read /etc/os-release")
        return False

@functools.lru_cache(maxsize=1)
def get_toolbox_engine() -> str:
    if _is_ubuntu_debian_arch():
        engines = detect_engines()
        return "podman" if "podman" in engines else "docker"
    return "podman"

@functools.lru_cache(maxsize=1)
def get_os_toolbox_cmd() -> str:
    return "distrobox" if _is_ubuntu_debian_arch() else "toolbox"

def get_installed_toolboxes(registry_match: str, specific_engine: str = None) -> list[dict]:
    """Returns a list of dicts with name, image, status, engine."""
    engines = [specific_engine] if specific_engine else detect_engines()
    toolboxes = []
    
    r_norm = registry_match.replace("docker.io/", "") if registry_match else ""

    for engine in engines:
        try:
            res = subprocess.run(
                [engine, "ps", "-a", "--format", "{{.Names}}|{{.Image}}|{{.Status}}|{{.CreatedAt}}"], 
                capture_output=True, text=True, check=True
            )
            for line in res.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 3:
                    continue
                
                name, image, status = parts[0], parts[1], parts[2]
                status = status.replace(PODMAN_NO_DATE_MARKER, "Unknown Date")
                
                created = parts[3].split()[0] if len(parts) >= 4 and parts[3] else ""
                
                i_norm = image.replace("docker.io/", "")
                if r_norm and r_norm not in i_norm:
                    continue

                toolboxes.append({
                    "name": name,
                    "image": image,
                    "status": status,
                    "created": created,
                    "engine": engine
                })
        except Exception:
            logger.exception(f"Failed to list installed toolboxes using {engine}")
            
    return toolboxes

def get_all_toolboxes(registry_match: str, config_data: dict) -> dict:
    engine = get_toolbox_engine()
    installed = get_installed_toolboxes(registry_match, engine)
    
    installed_dict = {tb["name"]: tb for tb in installed}
    
    grouped_toolboxes = {}
    
    for group in config_data.get("groups", []):
        group_name = group.get("name", "Unknown Group")
        grouped_toolboxes[group_name] = []
        
        for ctb in group.get("toolboxes", []):
            name = ctb["name"]
            tag = ctb.get("tag", "latest")
            desc = ctb.get("description", "")
            image = f"{registry_match}:{tag}"
            
            if name in installed_dict:
                tb = installed_dict[name]
                tb["args"] = ctb.get("engine_args", [])
                tb["description"] = desc
                tb["group"] = group_name
                grouped_toolboxes[group_name].append(tb)
                del installed_dict[name]
            else:
                grouped_toolboxes[group_name].append({
                    "name": name,
                    "image": image,
                    "description": desc,
                    "status": "Not Installed",
                    "created": "",
                    "engine": engine,
                    "args": ctb.get("engine_args", []),
                    "group": group_name
                })
                
    unsupported = []
    for tb in installed_dict.values():
        tb["args"] = []
        tb["description"] = ""
        tb["group"] = "Unsupported / Legacy"
        if "created" not in tb:
            tb["created"] = ""
        unsupported.append(tb)
        
    if unsupported:
        grouped_toolboxes["Unsupported / Legacy"] = unsupported
        
    return grouped_toolboxes

def create_toolbox(name: str, image: str, args: list[str]):
    cmd = get_os_toolbox_cmd()
    engine = get_toolbox_engine()
    os.environ["DBX_CONTAINER_MANAGER"] = engine
    
    # Pull first
    subprocess.run([engine, "pull", image], check=True)
    
    full_cmd = [cmd, "create", name, "--image", image]
    if args:
        full_cmd.append("--")
        full_cmd.extend(args)
    subprocess.run(full_cmd, check=True)

def delete_toolbox(name: str):
    cmd = get_os_toolbox_cmd()
    os.environ["DBX_CONTAINER_MANAGER"] = get_toolbox_engine()
    subprocess.run([cmd, "rm", "-f", name], check=True)

def get_remote_image_date(image: str) -> str:
    if not ("docker.io" in image or "kyuz0" in image):
        return None
    parts = image.split(':')
    repo = parts[0].replace('docker.io/', '')
    tag = parts[1] if len(parts) > 1 else "latest"
    
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags/{tag}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get("last_updated")
    except Exception:
        logger.exception(f"Failed to fetch remote image date for {image}")
        return None
