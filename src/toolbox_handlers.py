"""Toolbox-related handler methods extracted as a mixin for LlamaCockpitApp."""

from textual import on, work
from textual.widgets import Button, Label, Input, DataTable, Collapsible
from textual.containers import Vertical, VerticalScroll

from src.toolbox_manager import (
    get_all_toolboxes, get_installed_toolboxes, get_remote_image_date,
    create_toolbox, delete_toolbox, get_os_toolbox_cmd,
)
from src.model_manager import (
    get_default_toolbox, save_default_toolbox, get_active_platform,
    save_active_platform,
)
from src.config import get_platforms, get_platform
from src.widgets import ConfirmModal, SelectModal, SearchableSelect

import os


class ToolboxHandlersMixin:
    """Mixin providing toolbox management handlers for LlamaCockpitApp."""

    # ── Refresh ──────────────────────────────────────────────────────

    def refresh_toolboxes(self):
        self._mounting_tables = True

        platform = get_platform(self.active_platform_id)
        if not platform:
            self._mounting_tables = False
            return
        registry = platform.get("registry", "")
        grouped_data = get_all_toolboxes(registry, platform)

        self.toolboxes_dict = {}

        container = self.query_one("#toolbox_container", VerticalScroll)
        container.remove_children()

        default_tag = get_default_toolbox(self.active_platform_id)
        if not default_tag:
            default_tag = platform.get("default_toolbox_tag")

        for group_name, toolboxes in grouped_data.items():
            if not toolboxes: continue
            collapsed = group_name != "Official Toolboxes"
            table = DataTable(id=f"dt_{group_name.replace(' ', '_').replace('/', '')}", cursor_type="row")
            table.add_class("inactive-table")
            table.add_columns("Sel", "Toolbox Name", "Description", "Status", "Created", "Latest Release")

            for tb in toolboxes:
                self.toolboxes_dict[tb["name"]] = tb
                if tb["status"] == "Not Installed":
                    status_fmt = "[red]Needs Download[/red]"
                else:
                    status_fmt = "[green]Running[/green]" if "Up" in tb.get("status", "") else "[dim]Downloaded[/dim]"

                desc = tb.get('description', '')
                if default_tag and default_tag in tb.get('image', ''):
                    desc = f"[bold #e57373](Default)[/] {desc}"

                sel_fmt = "\\[x]" if tb['name'] in getattr(self, 'selected_toolboxes', set()) else "\\[ ]"
                table.add_row(sel_fmt, tb['name'], desc, status_fmt, tb.get('created', ''), "")

            btn_toggle = Button("Select/Deselect All", id=f"btn_toggle_{table.id}", classes="btn-toggle-all")
            col = Collapsible(Vertical(btn_toggle, table), title=f"{group_name} ({len(toolboxes)})", collapsed=collapsed)
            container.mount(col)

        def finish_mounting():
            first = True
            for dt in self.query(DataTable):
                if dt.id and dt.id.startswith("dt_"):
                    if first and dt.row_count > 0:
                        dt.remove_class("inactive-table")
                        try:
                            self.active_toolbox_name = dt.get_cell_at((dt.cursor_row, 1))
                        except Exception:
                            pass
                        first = False
                    else:
                        dt.add_class("inactive-table")

            self._mounting_tables = False

        self.call_next(finish_mounting)

    def refresh_server_images(self):
        sel_engine = self.query_one("#sel_engine", SearchableSelect)
        engine = sel_engine.value
        if not isinstance(engine, str) or not engine: return

        platform = get_platform(self.active_platform_id)
        registry = platform.get("registry", "") if platform else ""
        installed = get_installed_toolboxes(registry, engine)

        # Get all configured images for the platform from toolboxes.json
        configured_images = []
        if platform:
            for group in platform.get("groups", []):
                for tb in group.get("toolboxes", []):
                    tag = tb.get("tag", "latest")
                    configured_images.append(f"{registry}:{tag}")

        sel_image = self.query_one("#sel_image", SearchableSelect)
        images = sorted(set([tb['image'] for tb in installed] + configured_images))
        sel_image.set_options([(img, img) for img in images])
        if images:
            default_tag = get_default_toolbox(self.active_platform_id)
            if not default_tag and platform:
                default_tag = platform.get("default_toolbox_tag")

            selected = images[0]
            if default_tag:
                for img in images:
                    if default_tag in img:
                        selected = img
                        break
            sel_image.value = selected

    # ── Toolbox Handlers ─────────────────────────────────────────────

    def _handle_refresh(self):
        self.refresh_toolboxes()
        self.notify("Toolbox list refreshed.", timeout=3)

    def _handle_check_updates(self):
        tbs = self.get_selected_toolboxes()
        if not tbs:
            self.notify("No toolboxes selected.", severity="warning")
            return
        self.notify(f"Checking updates for {len(tbs)} toolbox(es)...", timeout=3)
        self._check_updates_bg(tbs)

    @work(thread=True, exclusive=True)
    def _check_updates_bg(self, tbs: list):
        for tb in tbs:
            remote_date = get_remote_image_date(tb['image'])
            if remote_date:
                remote_date_str = remote_date[:10]
                self.app.call_from_thread(self._update_toolbox_cell, tb['name'], 5, remote_date_str)
                created_date = self._get_toolbox_cell(tb['name'], 4)
                if created_date and remote_date_str > created_date:
                    self.app.call_from_thread(self._update_toolbox_cell, tb['name'], 3, "[yellow]Needs Update[/yellow]")
        self.app.call_from_thread(self.notify, "Update check complete.", timeout=3)

    def _handle_delete(self):
        tbs = self.get_selected_toolboxes()
        tbs = [tb for tb in tbs if tb["status"] != "Not Installed"]
        if not tbs:
            self.notify("No installed toolboxes selected.", severity="warning")
            return
        names = ", ".join([tb['name'] for tb in tbs])
        self._pending_delete_tbs = tbs
        self.app.push_screen(
            ConfirmModal(f"Are you sure you want to delete: {names}?"),
            self._on_delete_confirmed
        )

    def _on_delete_confirmed(self, confirmed: bool) -> None:
        if confirmed:
            tbs = self._pending_delete_tbs
            with self.suspend():
                for tb in tbs:
                    print(f"Deleting {tb['name']}...")
                    delete_toolbox(tb['name'])
            self.selected_toolboxes.clear()
            self.refresh_toolboxes()

    def _handle_create_update(self):
        tbs = self.get_selected_toolboxes()
        if not tbs:
            self.notify("No toolboxes selected.", severity="warning")
            return
        to_create, to_update, already_updated = [], [], []

        with self.suspend():
            print("\nChecking latest image versions from registry...")
        for tb in tbs:
            if tb["status"] == "Not Installed":
                to_create.append(tb)
            else:
                remote_date = get_remote_image_date(tb['image'])
                if remote_date:
                    remote_date_str = remote_date[:10]
                    if tb.get('created') and remote_date_str > tb.get('created', ''):
                        to_update.append(tb)
                    else:
                        already_updated.append(tb)
                else:
                    already_updated.append(tb)

        if already_updated:
            with self.suspend():
                print("\nThe following toolboxes are already up-to-date:")
                for tb in already_updated:
                    print(f"  - {tb['name']}")

        if not to_create and not to_update:
            with self.suspend():
                input("\nNothing to do. Press Enter to return to UI...")
            self.selected_toolboxes.clear()
            self.refresh_toolboxes()
            return

        if to_update:
            names = ", ".join([tb['name'] for tb in to_update])
            warning_msg = (
                f"The following toolboxes have updates available and will be DELETED and RECREATED:\n"
                f"  {names}\n\n"
                f"Any manually installed packages via apt/dnf inside them will be lost. Continue?"
            )
            self._pending_update_tbs = to_update
            self._pending_create_tbs = to_create
            self.app.push_screen(ConfirmModal(warning_msg), self._on_update_confirmed)
        else:
            self._do_create_toolboxes(to_create)

    def _on_update_confirmed(self, confirmed: bool) -> None:
        if not confirmed:
            return
        to_update = self._pending_update_tbs
        to_create = self._pending_create_tbs
        with self.suspend():
            for tb in to_update:
                delete_toolbox(tb['name'])
        self._do_create_toolboxes(to_create + to_update)

    def _do_create_toolboxes(self, tbs: list) -> None:
        with self.suspend():
            for tb in tbs:
                print(f"\nDownloading and creating toolbox {tb['name']}...")
                create_toolbox(tb['name'], tb['image'], tb.get('args', []))
            input("\nSuccess! Press Enter to return to UI...")
        self.selected_toolboxes.clear()
        self.refresh_toolboxes()

    def _handle_enter_toolbox(self):
        tb = self.get_selected_toolbox()
        if not tb:
            self.notify("Select exactly one toolbox to enter.", severity="warning")
            return
        if tb["status"] == "Not Installed":
            self.notify("Cannot enter a toolbox that is not installed.", severity="warning")
            return
        cmd = get_os_toolbox_cmd()
        with self.suspend():
            os.system(f"{cmd} enter {tb['name']}")

    # ── Toggle Select All ────────────────────────────────────────────

    def _handle_toggle_select_all(self, btn_id: str):
        dt_id = btn_id.replace("btn_toggle_", "")
        dt = self.query_one(f"#{dt_id}", DataTable)

        all_selected = all(
            dt.get_cell_at((i, 1)) in self.selected_toolboxes
            for i in range(dt.row_count)
        )

        for i in range(dt.row_count):
            name = dt.get_cell_at((i, 1))
            if all_selected:
                self.selected_toolboxes.discard(name)
                dt.update_cell_at((i, 0), "\\[ ]")
            else:
                self.selected_toolboxes.add(name)
                dt.update_cell_at((i, 0), "\\[x]")

    # ── Set Default ──────────────────────────────────────────────────

    def _handle_set_default(self):
        selected = self.get_selected_toolboxes()
        if not selected:
            self.notify("Please select a single toolbox to set as default.", severity="error")
            return
        if len(selected) > 1:
            self.notify("Please select exactly one toolbox to set as default.", severity="error")
            return

        tb = selected[0]
        image = tb.get("image", "")
        tag = image.split(":")[-1] if ":" in image else image

        if save_default_toolbox(self.active_platform_id, tag):
            self.notify(f"Set {tag} as default for platform {self.active_platform_id}.", severity="success", timeout=5)
            self.refresh_toolboxes()
            self.refresh_server_images()
        else:
            self.notify("Failed to save default toolbox configuration.", severity="error")

    # ── Platform Switch ──────────────────────────────────────────────

    def _handle_switch_platform(self):
        platforms = get_platforms()
        display_options = []
        for p in platforms:
            marker = "● " if p["id"] == self.active_platform_id else "  "
            display_options.append(f"{marker}{p['name']}  —  {p.get('description', '')}")
        self._switch_platforms = platforms
        self.app.push_screen(
            SelectModal("Select Platform:", display_options),
            self._on_platform_selected
        )

    def _on_platform_selected(self, choice_idx: int | None) -> None:
        if choice_idx is None:
            return
        platforms = self._switch_platforms
        if 0 <= choice_idx < len(platforms):
            new_id = platforms[choice_idx]["id"]
            if new_id == self.active_platform_id:
                return
            self.active_platform_id = new_id
            save_active_platform(new_id)
            self._update_platform_label()
            self.selected_toolboxes.clear()
            self.refresh_toolboxes()
            self.refresh_server_images()
            self.notify(f"Switched to {platforms[choice_idx]['name']}", timeout=3)

    # ── DataTable Helpers ────────────────────────────────────────────

    def _update_toolbox_cell(self, name: str, col: int, value: str):
        for dt in self.query(DataTable):
            if dt.id and dt.id.startswith("dt_"):
                for row_idx in range(dt.row_count):
                    if dt.get_cell_at((row_idx, 1)) == name:
                        dt.update_cell_at((row_idx, col), value)
                        return

    def _get_toolbox_cell(self, name: str, col: int):
        for dt in self.query(DataTable):
            if dt.id and dt.id.startswith("dt_"):
                for row_idx in range(dt.row_count):
                    if dt.get_cell_at((row_idx, 1)) == name:
                        return dt.get_cell_at((row_idx, col))
        return None
