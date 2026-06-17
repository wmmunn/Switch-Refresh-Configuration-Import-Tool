from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from .core import (
    PLACEHOLDERS,
    TTKBOOTSTRAP_AVAILABLE,
    LabNotesExtractorApp,
    apply_template,
    extract_config_values,
    read_text_file,
    tb,
    write_text_file,
)


APP_NAME = "Switch Refresh Configuration Import Tool"
APP_VERSION = "1.0.0"
TEMPLATE_DISPLAY_NAME = "Bundled Generic Refresh Build Template"
TEMPLATE_FILENAME = "generic_refresh_build_template.txt"
CONFIG_DISPLAY_NAME = "Bundled Generic Existing Switch Config"
CONFIG_FILENAME = "generic_existing_switch_config.txt"


def bundled_resource_path(filename: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return (
            Path(sys._MEIPASS)
            / "switch_refresh_config_import_tool"
            / "assets"
            / filename
        )
    return Path(__file__).resolve().parent / "assets" / filename


def load_bundled_template_text() -> str:
    return read_text_file(bundled_resource_path(TEMPLATE_FILENAME))


def load_bundled_config_text() -> str:
    return read_text_file(bundled_resource_path(CONFIG_FILENAME))


class SwitchRefreshConfigImportApp(LabNotesExtractorApp):
    app_name = APP_NAME
    app_version = APP_VERSION
    template_button_text = "Save Refresh Template"
    credit_text = "Sanitized distribution"

    def __init__(self, root):
        super().__init__(root)
        self.config_file_var.set(CONFIG_DISPLAY_NAME)
        self.template_file_var.set(TEMPLATE_DISPLAY_NAME)
        self.status_var.set(
            "Ready. Both generic input files are selected; choose an output file."
        )

    def browse_template_file(self):
        super().browse_template_file()

    def add_distribution_buttons(self, parent):
        self._button(
            parent,
            "Save Generic Existing Config",
            self.save_config,
            "secondary-outline",
        ).grid(row=4, column=2, sticky="e", pady=(8, 2))

    def save_config(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Existing Switch Config",
            initialfile="generic_existing_switch_config.txt",
            defaultextension=".txt",
            filetypes=[
                ("Text / Config Files", "*.txt *.cfg *.conf"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_bundled_config_text())
            self.config_file_var.set(filename)
            self.status_var.set(f"Generic existing switch config saved: {filename}")
            messagebox.showinfo(
                "Generic Config Saved",
                f"Generic existing switch config saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Generic Config Error", str(exc))

    def save_blank_template(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Refresh Build Template",
            initialfile="generic_refresh_build_template.txt",
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_bundled_template_text())
            self.template_file_var.set(filename)
            self.status_var.set(f"Generic refresh build template saved: {filename}")
            messagebox.showinfo(
                "Template Saved",
                f"Generic refresh build template saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Template Error", str(exc))

    def clear(self):
        self.config_file_var.set(CONFIG_DISPLAY_NAME)
        self.template_file_var.set(TEMPLATE_DISPLAY_NAME)
        self.output_file_var.set("")
        self.access_port_type_var.set("G")
        self.status_var.set(
            "Ready. Both generic input files are selected; choose an output file."
        )

    def validate_inputs(self):
        config_file = self.config_file_var.get().strip()
        template_file = self.template_file_var.get().strip()
        output_file = self.output_file_var.get().strip()

        if not config_file:
            messagebox.showerror(
                "Missing File",
                "Please select a sanitized existing switch configuration file.",
            )
            return None
        if not output_file:
            messagebox.showerror(
                "Missing File",
                "Please choose the completed refresh build output file.",
            )
            return None
        if config_file != CONFIG_DISPLAY_NAME and not Path(config_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Existing switch configuration file not found:\n{config_file}",
            )
            return None
        if template_file != TEMPLATE_DISPLAY_NAME and not Path(template_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Template file not found:\n{template_file}",
            )
            return None

        return config_file, template_file, output_file

    def run_extraction(self):
        validated = self.validate_inputs()
        if not validated:
            return

        config_file, template_file, output_file = validated
        try:
            if config_file == CONFIG_DISPLAY_NAME:
                config_text = load_bundled_config_text()
            else:
                config_text = read_text_file(config_file)
            if template_file == TEMPLATE_DISPLAY_NAME:
                template_text = load_bundled_template_text()
            else:
                template_text = read_text_file(template_file)

            values = extract_config_values(
                config_text,
                access_port_prefix=self.access_port_type_var.get(),
            )
            completed_notes = apply_template(template_text, values)
            write_text_file(output_file, completed_notes)

            found_count = sum(
                1 for value in values.values() if value != "NOT FOUND"
            )
            self.status_var.set(
                f"Complete. Extracted {found_count} of {len(values)} fields. Saved: {output_file}"
            )
            messagebox.showinfo(
                "Extraction Complete",
                "Refresh build template imported successfully.\n\n"
                f"Fields extracted: {found_count} of {len(values)}\n\n"
                f"Saved to:\n{output_file}",
            )
        except Exception as exc:
            messagebox.showerror("Extraction Failed", str(exc))
            self.status_var.set("Extraction failed. See error message.")


def main():
    root = tb.Window(themename="flatly") if TTKBOOTSTRAP_AVAILABLE else tk.Tk()
    SwitchRefreshConfigImportApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
