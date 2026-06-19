"""Model-related handler methods extracted as a mixin for LlamaCockpitApp."""

from textual import on
from textual.widgets import Input, DataTable

from src.model_manager import (
    scan_local_models, get_hf_quants, get_download_cmd,
    save_models_dir, is_quant_downloaded,
)
from src.widgets import ConfirmModal, SelectModal, SearchableSelect

import os
import subprocess


class ModelHandlersMixin:
    """Mixin providing model management handlers for LlamaCockpitApp."""

    # ── Refresh ──────────────────────────────────────────────────────

    def refresh_models(self):
        models = scan_local_models()
        self.current_models = models
        dt = self.query_one("#local_model_list", DataTable)
        dt.clear(columns=True)
        dt.add_columns("Filename")

        sel_model = self.query_one("#sel_model", SearchableSelect)
        model_opts = []

        try:
            sel_image = self.query_one("#sel_image", SearchableSelect)
            selected_image = sel_image.value or ""
        except Exception:
            selected_image = ""

        is_rocmfp4_image = "rocmfp4" in str(selected_image).lower()

        for m in models:
            dt.add_row(m["name"])

            is_rocmfp4_model = "rocmfp4" in m["name"].lower()
            if is_rocmfp4_image:
                if not is_rocmfp4_model:
                    continue
            else:
                if is_rocmfp4_model:
                    continue

            model_opts.append((m["name"], m["path"]))

        sel_model.set_options(model_opts)
        if model_opts:
            previous_val = sel_model.value
            if previous_val in [path for _, path in model_opts]:
                sel_model.value = previous_val
            else:
                sel_model.value = model_opts[0][1]
        else:
            sel_model.value = ""

    # ── Model Handlers ───────────────────────────────────────────────

    def _handle_scan_models(self):
        self.refresh_models()
        self.notify("Local models scanned.", timeout=3)

    def _handle_save_models_path(self):
        new_path = self.query_one("#inp_models_dir", Input).value
        if save_models_dir(new_path):
            self.notify(f"Models directory updated to {new_path}")
            self.refresh_models()
        else:
            self.notify("Failed to save models directory config.", severity="error")

    def _handle_download(self):
        repo = self.query_one("#sel_download_model", SearchableSelect).value
        if not isinstance(repo, str) or not repo:
            raw_val = self.query_one("#sel_download_model", SearchableSelect).query_one(Input).value.strip()
            if raw_val:
                repo = raw_val

        if not repo:
            self.notify("Please enter or select a model repository path.", severity="warning")
            return

        # ponytail: basic format gate — must look like "owner/model" to be a valid HF repo
        repo = repo.strip()
        if "/" not in repo or len(repo.split("/")) != 2 or not all(repo.split("/")):
            self.notify(f"Invalid repo format: '{repo}'. Expected 'owner/model' (e.g. unsloth/GLM-5.2-GGUF).", severity="error", timeout=5)
            return

        with self.suspend():
            print(f"\nQuerying Hugging Face for {repo}...")
        quants = get_hf_quants(repo)
        if not quants:
            self.notify(f"Hugging Face repository '{repo}' not found or contains no GGUF files.", severity="error", timeout=5)
            with self.suspend():
                print(f"Hugging Face repository '{repo}' not found or has no GGUF files.")
                try: input("Press Enter to return...")
                except: pass
            return

        display_options = []
        installed_flags = []
        with self.suspend():
            print("\nChecking local installation status...")
        for q in quants:
            if is_quant_downloaded(repo, q):
                display_options.append(f"[green]✓ Installed[/green]  {q}")
                installed_flags.append(True)
            else:
                display_options.append(q)
                installed_flags.append(False)

        self._download_quants = quants
        self._download_installed_flags = installed_flags
        self._download_repo = repo
        self.app.push_screen(
            SelectModal("Available Quantizations:", display_options),
            self._on_quant_selected
        )

    @on(Input.Submitted, "#sel_download_model Input")
    def on_download_input_submitted(self, event: Input.Submitted):
        self._handle_download()

    def _on_quant_selected(self, choice_idx: int | None) -> None:
        if choice_idx is None:
            return
        quants = self._download_quants
        installed_flags = self._download_installed_flags
        repo = self._download_repo
        if 0 <= choice_idx < len(quants):
            self._download_choice_idx = choice_idx
            if installed_flags[choice_idx]:
                self.app.push_screen(
                    ConfirmModal(f"The quant {quants[choice_idx]} appears to be already downloaded.\nDo you want to download it anyway?"),
                    self._on_redownload_confirmed
                )
            else:
                self._do_download_quant(repo, quants[choice_idx])

    def _on_redownload_confirmed(self, confirmed: bool) -> None:
        if confirmed:
            self._do_download_quant(self._download_repo, self._download_quants[self._download_choice_idx])

    def _do_download_quant(self, repo: str, quant: str) -> None:
        cmd = get_download_cmd(repo, quant)
        with self.suspend():
            print(f"\nRunning: HF_HUB_ENABLE_HF_TRANSFER=1 {' '.join(cmd)}")
            try:
                env = os.environ.copy()
                env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
                subprocess.run(cmd, env=env, check=True)
                print("\nDownload Complete!")
            except FileNotFoundError:
                print("\n[ERROR] 'hf' is not installed or not found in PATH.")
            except subprocess.CalledProcessError as e:
                print(f"\n[ERROR] Download failed with exit code {e.returncode}.")
            except Exception as e:
                print(f"\n[ERROR] An unexpected error occurred: {e}")
            try:
                input("\nPress Enter to return to UI...")
            except EOFError:
                pass
        self.refresh_models()
