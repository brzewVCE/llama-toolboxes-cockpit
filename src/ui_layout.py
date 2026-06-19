from textual.app import ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Button, Static, Label, Input, Checkbox, DataTable
from textual.containers import Vertical, Horizontal, VerticalScroll

from .widgets import SearchableSelect
from .model_manager import get_models_dir
from .config_manager import get_configs_dir

import pyfiglet
import importlib.metadata


def generate_banner() -> str:
    ascii_art = pyfiglet.figlet_format("Llama.cpp Cockpit", font="small")
    try:
        version = importlib.metadata.version("llama-cockpit")
        version_str = f"v{version}"
    except Exception:
        version_str = "v?.?.?"
        
    return f"[green]{ascii_art}[/green][dim]{version_str}[/dim]"


def compose_app() -> ComposeResult:
    """Build the full UI widget tree for LlamaCockpitApp."""
    yield Header(show_clock=True)
    yield Static(generate_banner(), id="banner")
    yield Horizontal(
        Label("", id="platform_label"),
        Button("Switch Platform", id="btn_switch_platform"),
        id="platform_row"
    )
    with TabbedContent(initial="tab-toolboxes"):
        with TabPane("Interactive Toolboxes", id="tab-toolboxes"):
            yield Vertical(
                Static("Manage and enter llama.cpp toolbox containers. The cockpit auto-detects your OS and selects the correct backend (toolbox on Fedora/RHEL, distrobox on Ubuntu/Arch).", classes="box"),
                VerticalScroll(id="toolbox_container"),
                Horizontal(
                    Button("Enter", id="btn_enter", variant="success"),
                    Button("Create/Update", id="btn_create_update", variant="warning"),
                    Button("Delete", id="btn_delete", variant="error"),
                    Button("Set Default", id="btn_set_default", variant="primary"),
                    Button("Check Updates", id="btn_check_updates"),
                    Button("Refresh", id="btn_refresh"),
                    id="btn_row"
                )
            )
        with TabPane("Server Mode", id="tab-server"):
            yield VerticalScroll(
                Static("Launch a Llama.cpp inference server directly without entering an interactive environment.", classes="box"),
                Horizontal(
                    Label("Engine", classes="inline-label"),
                    SearchableSelect(prompt="Select Container Engine", id="sel_engine"),
                    classes="inline-row"
                ),
                Horizontal(
                    Label("Image", classes="inline-label"),
                    SearchableSelect(prompt="Select Toolbox Image", id="sel_image"),
                    classes="inline-row"
                ),
                Horizontal(
                    Label("Model", classes="inline-label"),
                    SearchableSelect(prompt="Select Local Model", id="sel_model"),
                    classes="inline-row"
                ),
                Vertical(
                    Label("🎛️ Inference Profile", classes="zone-title"),
                    Horizontal(
                        Label("Profile", classes="inline-label"),
                        SearchableSelect(prompt="Select config to add...", id="sel_inference_profile"),
                        Button("Add", id="btn_add_profile", variant="success"),
                        Label("", id="lbl_profile_desc"),
                        classes="inline-row"
                    ),
                    Horizontal(id="profile_chips", classes="profile-chips"),
                    id="profile_zone", classes="model-zone"
                ),
                Horizontal(
                    Horizontal(Label("Context", classes="inline-label"), Input(placeholder="126976", id="inp_ctx", value="126976"), classes="short-field"),
                    Horizontal(Label("NGL", classes="inline-label"), Input(placeholder="999", id="inp_ngl", value="999"), classes="short-field"),
                    Horizontal(Label("Host", classes="inline-label"), Input(placeholder="localhost", id="inp_host", value="localhost"), classes="short-field"),
                    Horizontal(Label("Port", classes="inline-label"), Input(placeholder="8080", id="inp_port", value="8080"), classes="short-field"),
                    classes="inline-row"
                ),
                Horizontal(
                    Checkbox("Flash Attention (-fa 1)", id="chk_fa", value=True),
                    Checkbox("No Memory Mapping (--no-mmap)", id="chk_no_mmap", value=True),
                    classes="options-row"
                ),
                Horizontal(
                    Label("HIP Devices", classes="inline-label", id="lbl_gpu_devices"),
                    Input(placeholder="e.g. 0 (leave empty to unset)", id="inp_hip_devices", value=""),
                    classes="inline-row"
                ),
                Horizontal(
                    Label("Extra Args", classes="inline-label"),
                    Input(placeholder="e.g. --batch-size 512", id="inp_custom_args", value="--jinja"),
                    classes="inline-row"
                ),
                Horizontal(
                    Button("Start Server", id="btn_start_server", variant="primary"),
                    id="btn_row"
                )
            )
        with TabPane("Model Manager", id="tab-models"):
            with Vertical(id="model_manager_view"):
                # Zone 1: Hugging Face Downloader
                with Vertical(id="download_zone", classes="model-zone"):
                    yield Label("📥 HF Downloader", classes="zone-title")
                    with Horizontal(classes="inline-row"):
                        yield Label("Model Repo", classes="inline-label")
                        yield SearchableSelect(prompt="Search curated models or enter custom HF repo...", id="sel_download_model")
                        yield Button("Download", id="btn_download", variant="success")
                
                # Zone 2: Local Models Library
                with Vertical(id="local_zone", classes="model-zone"):
                    yield Label("📂 Local GGUF Directory", classes="zone-title")
                    with Horizontal(classes="inline-row"):
                        yield Label("Storage Path", classes="inline-label")
                        yield Input(placeholder="e.g. ~/models", id="inp_models_dir", value=str(get_models_dir()))
                        yield Button("Save Path", id="btn_save_models_path")
                        yield Button("Scan Local", id="btn_scan_models", variant="primary")
                    
                    yield DataTable(id="local_model_list", cursor_type="row")
        with TabPane("Config Manager", id="tab-configs"):
            with Vertical(id="config_manager_view"):
                # Zone 1: Config Directory Config & Scan
                with Vertical(id="config_dir_zone", classes="model-zone"):
                    yield Label("📂 Configs Directory", classes="zone-title")
                    with Horizontal(classes="inline-row"):
                        yield Label("Storage Path", classes="inline-label")
                        yield Input(placeholder="e.g. ~/.llama-cockpit/configs", id="inp_configs_dir", value=str(get_configs_dir()))
                        yield Button("Save Path", id="btn_save_configs_path")
                        yield Button("Scan Local", id="btn_scan_configs", variant="primary")
                    
                    yield DataTable(id="local_config_list", cursor_type="row")
                    
                # Zone 2: Config Editor
                with Vertical(id="config_editor_zone", classes="model-zone"):
                    yield Label("🛠️ Edit / Create Config", classes="zone-title")
                    with Horizontal(classes="inline-row"):
                        yield Label("Select Config", classes="inline-label")
                        yield SearchableSelect(prompt="Select a config to edit or create new...", id="sel_creator_config")
                        yield Button("New Config", id="btn_new_config", variant="primary")
                    
                    with Horizontal(classes="inline-row"):
                        yield Label("Config Name", classes="inline-label")
                        yield Input(placeholder="e.g. My Custom Run", id="inp_config_name")
                    
                    with Horizontal(classes="inline-row"):
                        yield Label("Commands/Args", classes="inline-label")
                        yield Input(placeholder="e.g. --temp 0.8 --top-p 0.95", id="inp_config_commands")

                    with Horizontal(classes="inline-row"):
                        yield Label("Model Filters", classes="inline-label")
                        yield Input(placeholder="e.g. *qwen*, *rocmfp4* (leave empty for global/loose)", id="inp_config_models")
                    
                    with Horizontal(id="config_btn_row"):
                        yield Button("Save Config", id="btn_save_config", variant="success")
                        yield Button("Delete Config", id="btn_delete_config", variant="error")
    yield Footer()
