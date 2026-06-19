"""Config-related handler methods extracted as a mixin for LlamaCockpitApp."""

import fnmatch

from textual import on
from textual.widgets import Input, Label, DataTable
from textual.containers import Vertical

from src.config import get_inference_profiles
from src.config_manager import (
    get_all_configs, save_custom_config, delete_custom_config_file,
    save_configs_dir,
)
from src.widgets import SearchableSelect


class ConfigHandlersMixin:
    """Mixin providing config management handlers for LlamaCockpitApp."""

    # ── Refresh ──────────────────────────────────────────────────────

    def refresh_configs(self, select_name: str = None):
        configs = get_all_configs()
        self.current_configs = configs

        # Populate DataTable
        dt = self.query_one("#local_config_list", DataTable)
        dt.clear(columns=True)
        dt.add_columns("Type", "Name", "Model Filters", "Commands/Args")
        for c in configs:
            t_str = "[cyan]Built-in[/cyan]" if not c.get("is_custom") else "[green]Custom[/green]"
            models_str = ", ".join(c.get("models", [])) or "*"
            dt.add_row(t_str, c["name"], models_str, c.get("args", ""))

        # Populate SearchableSelect dropdown
        sel = self.query_one("#sel_creator_config", SearchableSelect)
        options = []
        for c in configs:
            opt_label = f"\\[{c['name']}]" if c.get("is_custom") else c["name"]
            options.append((opt_label, c["name"]))
        sel.set_options(options)

        if select_name:
            sel.value = select_name
        else:
            sel.value = ""

    def refresh_server_profiles(self):
        sel_model = self.query_one("#sel_model", SearchableSelect)
        selected_path = str(sel_model.value) if sel_model.value else ""
        model_filename = selected_path.split("/")[-1] if selected_path else ""

        model_config = getattr(self, "_current_model_config", None)

        # Get curated/built-in profiles from models.json for this model
        curated_profiles = get_inference_profiles(model_config)

        # Get all configs (built-in and custom)
        # Filter them: keep those where model matches at least one pattern, OR models is empty/["*"]
        all_configs = get_all_configs()
        matching_configs = []
        for c in all_configs:
            patterns = c.get("models", [])
            # Global config if no patterns or only "*"
            if not patterns or patterns == ["*"]:
                matching_configs.append(c)
            elif model_filename:
                # Check if matches any pattern
                matches = False
                for p in patterns:
                    if fnmatch.fnmatch(model_filename.lower(), p.lower()):
                        matches = True
                        break
                if matches:
                    matching_configs.append(c)

        profile_zone = self.query_one("#profile_zone", Vertical)
        if curated_profiles or matching_configs:
            profile_zone.styles.display = "block"
            sel_profile = self.query_one("#sel_inference_profile", SearchableSelect)

            options = []
            # 1. Curated profiles from models.json
            for name in curated_profiles.keys():
                options.append((name, f"curated_{name}"))
            # 2. Scanned configurations (built-in or custom)
            for c in matching_configs:
                opt_label = f"\\[{c['name']}]" if c.get("is_custom") else c["name"]
                options.append((opt_label, f"config_{c['name']}"))

            sel_profile.set_options(options)
            if options:
                sel_profile.value = options[0][1]
        else:
            profile_zone.styles.display = "none"
            self.query_one("#sel_inference_profile", SearchableSelect).set_options([])
            self.query_one("#lbl_profile_desc", Label).update("")

    # ── Config Selection ─────────────────────────────────────────────

    def on_creator_config_selected(self, event: SearchableSelect.Changed):
        name = event.value
        if name:
            configs = getattr(self, "current_configs", [])
            selected_cfg = next((c for c in configs if c["name"] == name), None)
            if selected_cfg:
                self.query_one("#inp_config_name", Input).value = selected_cfg["name"]
                self.query_one("#inp_config_commands", Input).value = selected_cfg.get("args", "")
                self.query_one("#inp_config_models", Input).value = ", ".join(selected_cfg.get("models", []))

    def on_config_row_selected(self, event: DataTable.RowSelected):
        """When a config row is selected in the DataTable, load it into the editor."""
        try:
            row_data = event.data_table.get_row(event.row_key)
            name = row_data[1]  # Name column is at index 1
            if name:
                self.query_one("#sel_creator_config", SearchableSelect).value = name
        except Exception:
            logger.exception("Failed to handle config row selection")

    # ── Config Handlers ──────────────────────────────────────────────

    def _handle_new_config(self):
        self.query_one("#sel_creator_config", SearchableSelect).value = ""
        self.query_one("#inp_config_name", Input).value = ""
        self.query_one("#inp_config_commands", Input).value = ""
        self.query_one("#inp_config_models", Input).value = ""
        self.notify("Ready to create a new configuration.")

    def _handle_save_config(self):
        name = self.query_one("#inp_config_name", Input).value.strip()
        commands = self.query_one("#inp_config_commands", Input).value.strip()
        models_raw = self.query_one("#inp_config_models", Input).value.strip()

        if not name:
            self.notify("Config name cannot be empty.", severity="error")
            return

        models_list = [p.strip() for p in models_raw.split(",") if p.strip()]

        if save_custom_config(name, commands, models_list):
            self.notify(f"Configuration '{name}' saved.", severity="success")
            self.refresh_configs(select_name=name)
            self.refresh_server_profiles()
        else:
            self.notify("Failed to save configuration.", severity="error")

    def _handle_delete_config(self):
        name = self.query_one("#inp_config_name", Input).value.strip()
        if not name:
            self.notify("No configuration name specified to delete.", severity="warning")
            return

        configs = getattr(self, "current_configs", [])
        selected_cfg = next((c for c in configs if c["name"] == name), None)

        if not selected_cfg:
            self.notify(f"Configuration '{name}' not found.", severity="error")
            return

        if not selected_cfg.get("is_custom"):
            self.notify("Built-in configurations cannot be deleted.", severity="error")
            return

        filename = selected_cfg.get("filename")
        if delete_custom_config_file(filename):
            self.notify(f"Deleted configuration '{name}'.", severity="success")
            self.query_one("#inp_config_name", Input).value = ""
            self.query_one("#inp_config_commands", Input).value = ""
            self.query_one("#inp_config_models", Input).value = ""
            self.refresh_configs()
            self.refresh_server_profiles()
        else:
            self.notify("Failed to delete configuration file.", severity="error")

    def _handle_save_configs_path(self):
        new_path = self.query_one("#inp_configs_dir", Input).value.strip()
        if save_configs_dir(new_path):
            self.notify(f"Configs directory updated to {new_path}")
            self.refresh_configs()
            self.refresh_server_profiles()
        else:
            self.notify("Failed to save configs directory.", severity="error")

    def _handle_scan_configs(self):
        self.refresh_configs()
        self.refresh_server_profiles()
        self.notify("Configs directory scanned.")
