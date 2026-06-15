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


APP_NAME = "Generic Lab Notes Extractor"
APP_VERSION = "1.0.0"
BASELINE_DISPLAY_NAME = "Bundled Generic Baseline Lab Sheet"
BASELINE_FILENAME = "generic_baseline_lab_sheet.txt"
SAMPLE_CONFIG_DISPLAY_NAME = "Bundled Generic Sample Running-Config"
SAMPLE_CONFIG_FILENAME = "generic_sample_running_config.txt"


def bundled_resource_path(filename: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return (
            Path(sys._MEIPASS)
            / "generic_lab_notes_extractor"
            / "assets"
            / filename
        )
    return Path(__file__).resolve().parent / "assets" / filename


def load_bundled_baseline_text() -> str:
    return read_text_file(bundled_resource_path(BASELINE_FILENAME))


def load_bundled_sample_config_text() -> str:
    return read_text_file(bundled_resource_path(SAMPLE_CONFIG_FILENAME))


class SanitizedLabNotesExtractorApp(LabNotesExtractorApp):
    app_name = APP_NAME
    app_version = APP_VERSION
    template_button_text = "Save Generic Baseline"
    credit_text = "Sanitized distribution"

    def __init__(self, root):
        super().__init__(root)
        self.config_file_var.set(SAMPLE_CONFIG_DISPLAY_NAME)
        self.template_file_var.set(BASELINE_DISPLAY_NAME)
        self.status_var.set(
            "Ready. Both generic input files are selected; choose an output file."
        )

    def browse_template_file(self):
        super().browse_template_file()

    def add_distribution_buttons(self, parent):
        self._button(
            parent,
            "Save Generic Sample Config",
            self.save_sample_config,
            "secondary-outline",
        ).grid(row=4, column=2, sticky="e", pady=(8, 2))

    def save_sample_config(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Sample Running-Config",
            initialfile="generic_sample_running_config.txt",
            defaultextension=".txt",
            filetypes=[
                ("Text / Config Files", "*.txt *.cfg *.conf"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_bundled_sample_config_text())
            self.config_file_var.set(filename)
            self.status_var.set(f"Generic sample running-config saved: {filename}")
            messagebox.showinfo(
                "Generic Sample Saved",
                f"Generic sample running-config saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Generic Sample Error", str(exc))

    def save_blank_template(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Baseline Lab Sheet",
            initialfile="generic_baseline_lab_sheet.txt",
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
            write_text_file(filename, load_bundled_baseline_text())
            self.template_file_var.set(filename)
            self.status_var.set(f"Generic baseline saved: {filename}")
            messagebox.showinfo(
                "Baseline Saved",
                f"Generic baseline lab sheet saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Baseline Error", str(exc))

    def clear(self):
        self.config_file_var.set(SAMPLE_CONFIG_DISPLAY_NAME)
        self.template_file_var.set(BASELINE_DISPLAY_NAME)
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
                "Please select a sanitized old-switch running-config file.",
            )
            return None
        if not output_file:
            messagebox.showerror(
                "Missing File",
                "Please choose the completed lab notes output file.",
            )
            return None
        if config_file != SAMPLE_CONFIG_DISPLAY_NAME and not Path(config_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Running-config file not found:\n{config_file}",
            )
            return None
        if template_file != BASELINE_DISPLAY_NAME and not Path(template_file).exists():
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
            if config_file == SAMPLE_CONFIG_DISPLAY_NAME:
                config_text = load_bundled_sample_config_text()
            else:
                config_text = read_text_file(config_file)
            if template_file == BASELINE_DISPLAY_NAME:
                template_text = load_bundled_baseline_text()
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
                "Generic lab notes created successfully.\n\n"
                f"Fields extracted: {found_count} of {len(values)}\n\n"
                f"Saved to:\n{output_file}",
            )
        except Exception as exc:
            messagebox.showerror("Extraction Failed", str(exc))
            self.status_var.set("Extraction failed. See error message.")


def main():
    root = tb.Window(themename="flatly") if TTKBOOTSTRAP_AVAILABLE else tk.Tk()
    SanitizedLabNotesExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
