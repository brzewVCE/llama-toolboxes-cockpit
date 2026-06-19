from textual.app import App, ComposeResult
from textual.theme import Theme
from textual import on, events, work
from textual.widgets import Button, Label, Input, Checkbox, DataTable
from textual.containers import Horizontal
import os
import subprocess
import time

from src.toolbox_manager import detect_engines
from src.model_manager import get_active_platform
from src.server_runner import build_server_cmd
from src.config import (
    load_models, get_platform, get_model_config, get_inference_profiles, logger
)
from src.widgets import SearchableSelect
from src.ui_layout import compose_app

from src.toolbox_handlers import ToolboxHandlersMixin
from src.model_handlers import ModelHandlersMixin
from src.config_handlers import ConfigHandlersMixin


def _get_css_path() -> str:
    """Return absolute path to the bundled stylesheet."""
    return os.path.join(os.path.dirname(__file__), "assets", "style.tcss")


class LlamaCockpitApp(ToolboxHandlersMixin, ModelHandlersMixin, ConfigHandlersMixin, App):
    TITLE = "Llama.cpp Cockpit"
    CSS_PATH = [_get_css_path()]

    def compose(self) -> ComposeResult:
        yield from compose_app()

    def on_mount(self):
        cockpit_theme = Theme(
            name="cockpit-red",
            primary="#d32f2f",
            secondary="#b71c1c",
            accent="#e57373",
            foreground="#ffffff",
            background="#121212",
            surface="#1e1e1e",
            panel="#2a2a2a",
            warning="#ffa000",
            error="#d32f2f",
            success="#4caf50",
            dark=True,
        )
        self.register_theme(cockpit_theme)
        self.theme = "cockpit-red"
        
        self.active_platform_id = get_active_platform()
        self._update_platform_label()
        
        self.selected_toolboxes = set()
        self.refresh_toolboxes()
        self.refresh_models()
        self.check_app_updates()
        
        engines = detect_engines()
        sel_engine = self.query_one("#sel_engine", SearchableSelect)
        sel_engine.set_options([(e, e) for e in engines])
        if engines:
            sel_engine.value = engines[0]

        curated = load_models()
        sel_dl = self.query_one("#sel_download_model", SearchableSelect)
        dl_options = []
        for m in curated:
            compat = m.get("compatible_toolboxes")
            if compat:
                compat_str = ", ".join(compat)
                display_name = f"{m['name']} (Compatible with: {compat_str})"
            else:
                display_name = m["name"]
            dl_options.append((display_name, m["repo"]))
        sel_dl.set_options(dl_options)
        self.refresh_configs()

    @work(thread=True)
    def check_app_updates(self):
        import urllib.request
        import json
        import importlib.metadata
        try:
            current_version = importlib.metadata.version("llama-cockpit")
            req = urllib.request.Request("https://api.github.com/repos/kyuz0/llama-toolboxes-cockpit/tags")
            req.add_header('User-Agent', 'Llama-Cockpit-Update-Checker')
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                if data:
                    latest_tag = data[0]['name']
                    latest_version = latest_tag.lstrip('v')
                    
                    curr_parts = tuple(int(x) for x in current_version.split('.') if x.isdigit())
                    latest_parts = tuple(int(x) for x in latest_version.split('.') if x.isdigit())
                    
                    if latest_parts > curr_parts:
                        msg = f"Update available: v{latest_version} (Current: v{current_version}).\nRun `pipx upgrade llama-cockpit` to update."
                        self.app.call_from_thread(self.notify, msg, title="Cockpit Update Available", severity="information", timeout=15)
        except Exception:
            logger.exception("Failed to check for app updates")

    def _update_platform_label(self):
        platform = get_platform(self.active_platform_id)
        if platform:
            name = platform.get("name", self.active_platform_id)
            desc = platform.get("description", "")
            self.query_one("#platform_label", Label).update(f"Platform: {name}  —  {desc}")
        else:
            self.query_one("#platform_label", Label).update(f"Platform: {self.active_platform_id}")

        try:
            lbl_gpu = self.query_one("#lbl_gpu_devices", Label)
            inp_gpu = self.query_one("#inp_hip_devices", Input)
            if "intel" in self.active_platform_id.lower():
                lbl_gpu.update("Level Zero Devices")
                inp_gpu.placeholder = "e.g. 0.0 (leave empty to unset)"
            else:
                lbl_gpu.update("HIP Devices")
                inp_gpu.placeholder = "e.g. 0 (leave empty to unset)"
        except Exception:
            logger.exception("Failed to update platform label")

    # ── DataTable Selection Logic ────────────────────────────────────

    def _toggle_row_selection(self, dt: DataTable, cursor_row: int):
        try:
            name = dt.get_cell_at((cursor_row, 1))
            if name in self.selected_toolboxes:
                self.selected_toolboxes.remove(name)
                dt.update_cell_at((cursor_row, 0), "\\[ ]")
            else:
                self.selected_toolboxes.add(name)
                dt.update_cell_at((cursor_row, 0), "\\[x]")
        except Exception:
            logger.exception("Failed to toggle row selection")

    @on(events.MouseUp)
    def on_mouse_up(self, event: events.MouseUp):
        if isinstance(event.control, DataTable) and event.control.id and event.control.id.startswith("dt_"):
            self._last_dt_click_time = time.time()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected):
        if event.control.id and event.control.id.startswith("dt_"):
            self._toggle_row_selection(event.control, event.cursor_row)

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted):
        if getattr(self, "_mounting_tables", False):
            return
            
        if event.control.id and event.control.id.startswith("dt_"):
            if time.time() - getattr(self, "_last_dt_click_time", 0.0) < 0.1:
                self._toggle_row_selection(event.control, event.cursor_row)
                
            try:
                name = event.control.get_cell_at((event.cursor_row, 1))
                self.active_toolbox_name = name
                
                for dt in self.query(DataTable):
                    if dt.id and dt.id.startswith("dt_"):
                        if dt == event.control:
                            dt.remove_class("inactive-table")
                        else:
                            dt.add_class("inactive-table")
            except Exception:
                logger.exception("Failed to highlight row in DataTable")

    def on_descendant_focus(self, event: events.DescendantFocus):
        widget = event.widget
        if isinstance(widget, DataTable) and widget.id and widget.id.startswith("dt_"):
            for dt in self.query(DataTable):
                if dt.id and dt.id.startswith("dt_"):
                    if dt == widget:
                        dt.remove_class("inactive-table")
                        try:
                            self.active_toolbox_name = dt.get_cell_at((dt.cursor_row, 1))
                        except Exception:
                            logger.exception("Failed to get cell value on focus")
                    else:
                        dt.add_class("inactive-table")

    # ── Toolbox Selection Helpers ────────────────────────────────────

    def get_selected_toolboxes(self):
        tb_dict = getattr(self, 'toolboxes_dict', {})
        selected = []
        if getattr(self, 'selected_toolboxes', set()):
            for name in self.selected_toolboxes:
                if name in tb_dict:
                    selected.append(tb_dict[name])
        return selected

    def get_selected_toolbox(self):
        tb_dict = getattr(self, 'toolboxes_dict', {})
        if getattr(self, 'selected_toolboxes', set()) and len(self.selected_toolboxes) == 1:
            return tb_dict.get(list(self.selected_toolboxes)[0])
        return None

    # ── Config & Model Event Handlers (Scanned by Metaclass) ──────────

    @on(SearchableSelect.Changed, "#sel_creator_config")
    def on_creator_config_selected(self, event: SearchableSelect.Changed):
        super().on_creator_config_selected(event)

    @on(DataTable.RowSelected, "#local_config_list")
    def on_config_row_selected(self, event: DataTable.RowSelected):
        super().on_config_row_selected(event)

    @on(Input.Submitted, "#sel_download_model Input")
    def on_download_input_submitted(self, event: Input.Submitted):
        super().on_download_input_submitted(event)

    # ── Server Mode Event Handlers ───────────────────────────────────

    @on(SearchableSelect.Changed, "#sel_engine")
    def on_engine_selected(self, event: SearchableSelect.Changed):
        self.refresh_server_images()

    @on(SearchableSelect.Changed, "#sel_image")
    def on_image_selected(self, event: SearchableSelect.Changed):
        self.refresh_models()

    @on(SearchableSelect.Changed, "#sel_model")
    def on_model_selected(self, event: SearchableSelect.Changed):
        """When a model is selected, configure inference profile zone and extra args."""
        selected_path = str(event.value) if event.value else ""
        model_config = get_model_config(selected_path)
        
        # Store current model config for use by other handlers
        self._current_model_config = model_config
        
        # Reset Extra Args to base immediately so all change handlers start with a clean state
        inp = self.query_one("#inp_custom_args", Input)
        base_arg = "--no-jinja" if (model_config and model_config.get("no_jinja")) else "--jinja"
        self._expected_custom_args = base_arg
        inp.value = base_arg
        
        # Clear selected profiles
        self._selected_profiles = []
        self._refresh_profile_chips()
        
        # ── Inference Profile Zone ──────────────────────────────────────
        self.refresh_server_profiles()
        
        self._rebuild_extra_args()

    @on(Button.Pressed, "#btn_add_profile")
    def on_add_profile(self, event: Button.Pressed):
        """Add the currently selected profile to the active list."""
        sel_profile = self.query_one("#sel_inference_profile", SearchableSelect)
        profile_val = str(sel_profile.value) if sel_profile.value else ""
        if not profile_val:
            return
        
        selected = getattr(self, "_selected_profiles", [])
        # No duplicates
        if profile_val in selected:
            self.notify("Config already added.", severity="warning")
            return
        
        selected.append(profile_val)
        self._selected_profiles = selected
        self._refresh_profile_chips()
        self._rebuild_extra_args()

    @on(Button.Pressed, ".profile-chip")
    def on_remove_profile_chip(self, event: Button.Pressed):
        """Remove a profile chip when clicked."""
        chip_name = event.button.name or ""
        try:
            idx = int(chip_name)
        except (ValueError, TypeError):
            return
        selected = getattr(self, "_selected_profiles", [])
        if 0 <= idx < len(selected):
            selected.pop(idx)
            self._selected_profiles = selected
            self._refresh_profile_chips()
            self._rebuild_extra_args()

    def _refresh_profile_chips(self):
        """Rebuild the horizontal row of profile chips from _selected_profiles."""
        chips_container = self.query_one("#profile_chips", Horizontal)
        chips_container.remove_children()
        selected = getattr(self, "_selected_profiles", [])
        for i, prof_val in enumerate(selected):
            label = self._profile_val_to_label(prof_val)
            chip = Button(f"✕ {label}", name=str(i), variant="error", classes="profile-chip")
            chips_container.mount(chip)

    def _profile_val_to_label(self, profile_val: str) -> str:
        """Convert a profile value key to a human-readable label."""
        if profile_val.startswith("curated_"):
            return profile_val[8:]
        elif profile_val.startswith("config_"):
            return f"\\[{profile_val[7:]}]"
        return profile_val

    @on(Input.Changed, "#inp_custom_args")
    def on_custom_args_changed(self, event: Input.Changed):
        """Track when user manually edits Extra Args."""
        if getattr(self, "_expected_custom_args", None) == event.value:
            return
        
        # User is manually editing
        self.query_one("#lbl_profile_desc", Label).update("Manual edit")

    def _rebuild_extra_args(self):
        """Rebuild the Extra Args field from base + all selected profile args.
        
        Merges args from all selected profiles in order.
        """
        inp = self.query_one("#inp_custom_args", Input)
        model_config = getattr(self, "_current_model_config", None)
        base_arg = "--no-jinja" if (model_config and model_config.get("no_jinja")) else "--jinja"
        
        selected = getattr(self, "_selected_profiles", [])
        
        # Start from base
        merged = base_arg
        
        # Merge each selected profile's args in order
        for profile_val in selected:
            profile_args = self._get_profile_args(profile_val)
            if profile_args:
                merged = self._merge_args(merged, profile_args)
        
        self._expected_custom_args = merged
        inp.value = merged

    def _get_profile_args(self, profile_val: str) -> str:
        """Get the args string for a given profile value."""
        model_config = getattr(self, "_current_model_config", None)
        
        if profile_val.startswith("curated_"):
            curated_name = profile_val[8:]
            profiles = get_inference_profiles(model_config)
            if curated_name in profiles:
                return profiles[curated_name].get("args", "")
        elif profile_val.startswith("config_"):
            cfg_name = profile_val[7:]
            configs = getattr(self, "current_configs", [])
            selected_cfg = next((c for c in configs if c["name"] == cfg_name), None)
            if selected_cfg:
                return selected_cfg.get("args", "")
        return ""

    @staticmethod
    def _remove_flags(arg_str: str, flags_to_remove: list) -> str:
        """Remove specified flags and their values from the argument string."""
        import shlex
        if not arg_str:
            return ""
        try:
            tokens = shlex.split(arg_str)
        except Exception:
            logger.exception("Failed to shlex.split argument string")
            return arg_str
            
        new_tokens = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in flags_to_remove:
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                    i += 2
                else:
                    i += 1
            else:
                new_tokens.append(token)
                i += 1
        return " ".join(shlex.quote(t) for t in new_tokens)

    @staticmethod
    def _merge_args(base: str, override: str) -> str:
        """Merge two argument strings. Override args replace matching flags in base, new ones are appended."""
        import shlex
        
        if not override:
            return base
        if not base:
            return override
            
        base_tokens = shlex.split(base)
        override_tokens = shlex.split(override)
        
        # Parse into ordered list of (flag, value_or_None) pairs
        def parse_flags(tokens):
            flags = []
            i = 0
            while i < len(tokens):
                token = tokens[i]
                if token.startswith("-"):
                    # Check if next token is a value (not a flag)
                    if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                        flags.append((token, tokens[i + 1]))
                        i += 2
                    else:
                        flags.append((token, None))
                        i += 1
                else:
                    # Standalone value (shouldn't normally happen but be safe)
                    flags.append((token, None))
                    i += 1
            return flags
        
        base_flags = parse_flags(base_tokens)
        override_flags = parse_flags(override_tokens)
        
        # Build result: start with base, override matching, append new
        override_map = {f: v for f, v in override_flags}
        override_keys_used = set()
        
        result = []
        for flag, val in base_flags:
            if flag in override_map:
                # Replace with override value
                result.append((flag, override_map[flag]))
                override_keys_used.add(flag)
            else:
                result.append((flag, val))
        
        # Append any override flags not already in base
        for flag, val in override_flags:
            if flag not in override_keys_used:
                result.append((flag, val))
        
        # Serialize back
        parts = []
        for flag, val in result:
            parts.append(flag)
            if val is not None:
                parts.append(val)
        return " ".join(parts)

    # ── Button Dispatch ──────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed):
        handlers = {
            "btn_refresh": self._handle_refresh,
            "btn_scan_models": self._handle_scan_models,
            "btn_check_updates": self._handle_check_updates,
            "btn_delete": self._handle_delete,
            "btn_create_update": self._handle_create_update,
            "btn_enter": self._handle_enter_toolbox,
            "btn_start_server": self._handle_start_server,
            "btn_save_models_path": self._handle_save_models_path,
            "btn_download": self._handle_download,
            "btn_switch_platform": self._handle_switch_platform,
            "btn_set_default": self._handle_set_default,
            "btn_save_configs_path": self._handle_save_configs_path,
            "btn_scan_configs": self._handle_scan_configs,
            "btn_new_config": self._handle_new_config,
            "btn_save_config": self._handle_save_config,
            "btn_delete_config": self._handle_delete_config,
        }

        btn_id = event.button.id
        if btn_id in handlers:
            handlers[btn_id]()
        elif btn_id and btn_id.startswith("btn_toggle_dt_"):
            self._handle_toggle_select_all(btn_id)

    # ── Server Handler ───────────────────────────────────────────────

    def _handle_start_server(self):
        engine = self.query_one("#sel_engine", SearchableSelect).value
        image = self.query_one("#sel_image", SearchableSelect).value
        model_path = self.query_one("#sel_model", SearchableSelect).value
        ctx = self.query_one("#inp_ctx", Input).value
        ngl = self.query_one("#inp_ngl", Input).value
        host = self.query_one("#inp_host", Input).value
        port = self.query_one("#inp_port", Input).value
        use_fa = self.query_one("#chk_fa", Checkbox).value
        use_no_mmap = self.query_one("#chk_no_mmap", Checkbox).value
        custom_args = self.query_one("#inp_custom_args", Input).value
        hip_devices = self.query_one("#inp_hip_devices", Input).value

        # Check compatibility
        is_rocmfp4_image = "rocmfp4" in str(image).lower()
        is_rocmfp4_model = model_path and "rocmfp4" in str(model_path).lower()
        
        if is_rocmfp4_image and not is_rocmfp4_model:
            self.notify("The rocmfp4 toolbox only supports rocmfp4 quantized models.", severity="error")
            return
            
        if is_rocmfp4_model and not is_rocmfp4_image:
            self.notify("rocmfp4 models require a rocmfp4 compatible toolbox.", severity="error")
            return
            
        if model_path:
            model_config = get_model_config(model_path)
            if model_config and "compatible_toolboxes" in model_config:
                allowed = model_config["compatible_toolboxes"]
                image_lower = str(image).lower()
                compatible = any(alt.lower() in image_lower for alt in allowed)
                if not compatible:
                    allowed_str = ", ".join(allowed)
                    self.notify(f"Model compatibility error: Only supported on {allowed_str}", severity="error")
                    return

        if engine and image and model_path and ctx.isdigit():
            ngl_val = int(ngl) if ngl.isdigit() else 999
            
            engine_args = None
            if hasattr(self, "toolboxes_dict"):
                for tb in self.toolboxes_dict.values():
                    if tb.get("image") == image:
                        engine_args = tb.get("args")
                        break

            cmd = build_server_cmd(
                engine, image, model_path, int(ctx), use_fa, use_no_mmap, 
                custom_args, host, port, ngl_val, 
                hip_devices=hip_devices, 
                platform_id=self.active_platform_id, 
                engine_args=engine_args
            )
            with self.suspend():
                print(f"\nStarting server with command:\n{' '.join(cmd)}\n")
                print("Press Ctrl+C to stop the server and return to the UI.\n")
                subprocess.run(cmd)


def cli_main():
    app = LlamaCockpitApp()
    app.run()

if __name__ == "__main__":
    cli_main()
