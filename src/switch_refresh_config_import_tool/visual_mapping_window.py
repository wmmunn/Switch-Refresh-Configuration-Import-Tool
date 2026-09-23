"""Tkinter window for interactive source-to-target port mapping."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .visual_mapping import (
    ROLE_ACCESS,
    ROLE_EMPTY,
    ROLE_IGNORED,
    ROLE_PORT_CHANNEL_MEMBER,
    ROLE_UPLINK,
    ROLE_UNPLACEABLE,
    TARGET_CAGE_UPLINK,
    PortMappingPair,
    SourcePortCell,
    TargetPortCell,
    build_visual_mapping_status,
    clear_mapping,
    occupancy,
    set_mapping,
    source_cell_detail,
    target_cell_detail,
)


ROLE_FILL = {
    ROLE_ACCESS: "#2b6cb0",
    ROLE_UPLINK: "#c05621",
    ROLE_PORT_CHANNEL_MEMBER: "#6b46c1",
    ROLE_EMPTY: "#718096",
    ROLE_IGNORED: "#a0aec0",
    ROLE_UNPLACEABLE: "#744210",
}

CELL_WIDTH = 28
CELL_HEIGHT = 22
CELL_GAP = 4
MEMBER_LEFT = 16
PORTS_PER_ROW = 24
CANVAS_BACKGROUND = "#f7fafc"


ApplyCallback = Callable[[tuple[PortMappingPair, ...]], None]


def open_visual_mapping_window(
    parent: tk.Misc,
    source_cells: tuple[SourcePortCell, ...],
    target_cells: tuple[TargetPortCell, ...],
    initial_pairs: tuple[PortMappingPair, ...],
    on_apply: ApplyCallback,
) -> tk.Toplevel:
    """Open the port-map window. Returns the Toplevel for tests."""
    window = VisualMappingWindow(
        parent,
        source_cells,
        target_cells,
        initial_pairs,
        on_apply,
    )
    return window.top


class VisualMappingWindow:
    def __init__(
        self,
        parent: tk.Misc,
        source_cells: tuple[SourcePortCell, ...],
        target_cells: tuple[TargetPortCell, ...],
        initial_pairs: tuple[PortMappingPair, ...],
        on_apply: ApplyCallback,
    ) -> None:
        self.source_cells = source_cells
        self.target_cells = target_cells
        self.pairs = initial_pairs
        self.on_apply = on_apply
        self.selected_source: str | None = None
        self.source_item_ids: dict[str, int] = {}
        self.target_item_ids: dict[str, int] = {}

        self.top = tk.Toplevel(parent)
        self.top.title("Interactive Port Map")
        self.top.geometry("1280x780")
        self.top.minsize(1100, 640)

        self.status_var = tk.StringVar()
        self.selection_var = tk.StringVar(value="Select a source port, then a target port.")
        self.warning_var = tk.StringVar()

        self._build_layout()
        self._draw_faceplates()
        self._refresh_status()

    def _build_layout(self) -> None:
        header = ttk.Frame(self.top, padding=12)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Interactive Port Map",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Click a source port, then a target port. Uplinks and "
                "port-channel members must be mapped explicitly or they stay "
                "blank / follow access-port rules. Apply writes these pairs "
                "into the target profile for this run."
            ),
            wraplength=1220,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        legend = ttk.Frame(self.top, padding=(12, 0, 12, 8))
        legend.pack(fill="x")
        self._add_legend_swatch(legend, "Access", ROLE_FILL[ROLE_ACCESS])
        self._add_legend_swatch(legend, "Uplink", ROLE_FILL[ROLE_UPLINK])
        self._add_legend_swatch(legend, "Port-channel member", ROLE_FILL[ROLE_PORT_CHANNEL_MEMBER])
        self._add_legend_swatch(legend, "Empty", ROLE_FILL[ROLE_EMPTY])
        ttk.Label(
            legend,
            text="Orange outline = unmapped uplink or port-channel member. "
            "Red fill = collision. Green outline = mapped.",
        ).pack(side="left", padx=(16, 0))

        ttk.Label(
            self.top,
            textvariable=self.selection_var,
            padding=(12, 0, 12, 4),
            wraplength=1220,
            justify="left",
        ).pack(fill="x")
        ttk.Label(
            self.top,
            textvariable=self.status_var,
            padding=(12, 0, 12, 2),
            wraplength=1220,
            justify="left",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x")
        ttk.Label(
            self.top,
            textvariable=self.warning_var,
            padding=(12, 0, 12, 8),
            wraplength=1220,
            justify="left",
            foreground="#9b2c2c",
        ).pack(fill="x")

        boards = ttk.Frame(self.top, padding=(12, 0, 12, 8))
        boards.pack(fill="both", expand=True)
        boards.columnconfigure(0, weight=1)
        boards.columnconfigure(1, weight=1)
        boards.rowconfigure(1, weight=1)

        ttk.Label(boards, text="Source switch", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(boards, text="Target switch", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=1, sticky="w"
        )

        self.source_canvas = self._build_scroll_canvas(boards, 0)
        self.target_canvas = self._build_scroll_canvas(boards, 1)
        self.source_canvas.bind("<Button-1>", self._on_source_click)
        self.target_canvas.bind("<Button-1>", self._on_target_click)

        actions = ttk.Frame(self.top, padding=12)
        actions.pack(fill="x")
        ttk.Button(actions, text="Unmap Selected Source", command=self._unmap_selected).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(actions, text="Clear Map", command=self._clear_map).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Apply To This Run", command=self._apply).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Close", command=self.top.destroy).pack(side="right")

    def _add_legend_swatch(self, parent: ttk.Frame, label: str, color: str) -> None:
        swatch = tk.Canvas(parent, width=14, height=14, highlightthickness=0)
        swatch.create_rectangle(0, 0, 14, 14, fill=color, outline="#2d3748")
        swatch.pack(side="left")
        ttk.Label(parent, text=label).pack(side="left", padx=(4, 12))

    def _build_scroll_canvas(self, parent: ttk.Frame, column: int) -> tk.Canvas:
        frame = ttk.Frame(parent)
        frame.grid(row=1, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(frame, background=CANVAS_BACKGROUND, highlightthickness=1)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=canvas.xview)
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        return canvas

    def _draw_faceplates(self) -> None:
        self.source_item_ids = self._draw_source_board()
        self.target_item_ids = self._draw_target_board()

    def _draw_source_board(self) -> dict[str, int]:
        canvas = self.source_canvas
        canvas.delete("all")
        item_ids: dict[str, int] = {}
        mapped = {pair.source_interface: pair.target_interface for pair in self.pairs}
        claimed = occupancy(self.pairs)
        collision_sources = {
            source
            for sources in claimed.values()
            if len(sources) > 1
            for source in sources
        }

        y = 16
        grouped: dict[int | None, list[SourcePortCell]] = {}
        unplaced: list[SourcePortCell] = []
        for cell in self.source_cells:
            if cell.role == ROLE_IGNORED:
                continue
            if cell.member is None or cell.port is None:
                unplaced.append(cell)
                continue
            grouped.setdefault(cell.member, []).append(cell)

        for member in sorted(key for key in grouped if key is not None):
            canvas.create_text(
                MEMBER_LEFT,
                y,
                text=f"Source member {member}",
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            )
            y += 18
            row_ports = sorted(grouped[member], key=lambda cell: cell.port or 0)
            y = self._draw_source_row(
                canvas,
                row_ports,
                y,
                mapped,
                collision_sources,
                item_ids,
            )
            y += 12

        if unplaced:
            canvas.create_text(
                MEMBER_LEFT,
                y,
                text="Unplaced / other source ports",
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            )
            y += 18
            y = self._draw_source_row(
                canvas,
                unplaced,
                y,
                mapped,
                collision_sources,
                item_ids,
                wide=True,
            )

        canvas.configure(scrollregion=(0, 0, 24 * (CELL_WIDTH + CELL_GAP) + 40, y + 20))
        return item_ids

    def _draw_source_row(
        self,
        canvas: tk.Canvas,
        cells: list[SourcePortCell],
        y: int,
        mapped: dict[str, str],
        collision_sources: set[str],
        item_ids: dict[str, int],
        wide: bool = False,
    ) -> int:
        x = MEMBER_LEFT
        row_y = y
        for index, cell in enumerate(cells):
            if index and index % PORTS_PER_ROW == 0:
                row_y += CELL_HEIGHT + CELL_GAP + 4
                x = MEMBER_LEFT
            width = 120 if wide else CELL_WIDTH
            fill = ROLE_FILL.get(cell.role, "#4a5568")
            if cell.name in collision_sources:
                fill = "#c53030"
            outline = "#2d3748"
            width_outline = 1
            if cell.name == self.selected_source:
                outline = "#d69e2e"
                width_outline = 3
            elif cell.name in mapped:
                outline = "#276749"
                width_outline = 2
            elif cell.role in {ROLE_UPLINK, ROLE_PORT_CHANNEL_MEMBER}:
                outline = "#dd6b20"
                width_outline = 2

            item = canvas.create_rectangle(
                x,
                row_y,
                x + width,
                row_y + CELL_HEIGHT,
                fill=fill,
                outline=outline,
                width=width_outline,
                tags=("source", cell.name),
            )
            label = cell.name if wide else str(cell.port)
            canvas.create_text(
                x + width / 2,
                row_y + CELL_HEIGHT / 2,
                text=label,
                fill="white",
                font=("Segoe UI", 7, "bold"),
                tags=("source", cell.name),
            )
            item_ids[cell.name] = item
            x += width + CELL_GAP
        return row_y + CELL_HEIGHT + CELL_GAP

    def _draw_target_board(self) -> dict[str, int]:
        canvas = self.target_canvas
        canvas.delete("all")
        item_ids: dict[str, int] = {}
        claimed = occupancy(self.pairs)
        selected_target = None
        if self.selected_source:
            for pair in self.pairs:
                if pair.source_interface == self.selected_source:
                    selected_target = pair.target_interface
                    break

        y = 16
        members = sorted({cell.member for cell in self.target_cells})
        for member in members:
            canvas.create_text(
                MEMBER_LEFT,
                y,
                text=f"Target member {member} access",
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            )
            y += 18
            access_cells = [
                cell
                for cell in self.target_cells
                if cell.member == member and cell.cage != TARGET_CAGE_UPLINK
            ]
            y = self._draw_target_row(canvas, access_cells, y, claimed, selected_target, item_ids)
            y += 8
            canvas.create_text(
                MEMBER_LEFT,
                y,
                text=f"Target member {member} uplink slots",
                anchor="w",
                font=("Segoe UI", 9, "bold"),
                fill="#c05621",
            )
            y += 18
            uplink_cells = [
                cell
                for cell in self.target_cells
                if cell.member == member and cell.cage == TARGET_CAGE_UPLINK
            ]
            y = self._draw_target_row(canvas, uplink_cells, y, claimed, selected_target, item_ids)
            y += 12

        canvas.configure(scrollregion=(0, 0, 24 * (CELL_WIDTH + CELL_GAP) + 40, y + 20))
        return item_ids

    def _draw_target_row(
        self,
        canvas: tk.Canvas,
        cells: list[TargetPortCell],
        y: int,
        claimed: dict[str, tuple[str, ...]],
        selected_target: str | None,
        item_ids: dict[str, int],
    ) -> int:
        x = MEMBER_LEFT
        row_y = y
        for index, cell in enumerate(cells):
            if index and index % PORTS_PER_ROW == 0:
                row_y += CELL_HEIGHT + CELL_GAP + 4
                x = MEMBER_LEFT
            owners = claimed.get(cell.name, ())
            fill = ROLE_FILL[ROLE_UPLINK] if cell.cage == TARGET_CAGE_UPLINK else "#2f855a"
            if len(owners) > 1:
                fill = "#c53030"
            elif owners:
                fill = "#276749"
            outline = "#2d3748"
            width_outline = 1
            if cell.name == selected_target:
                outline = "#d69e2e"
                width_outline = 3
            elif not owners and cell.cage == TARGET_CAGE_UPLINK:
                outline = "#dd6b20"
                width_outline = 2

            item = canvas.create_rectangle(
                x,
                row_y,
                x + CELL_WIDTH,
                row_y + CELL_HEIGHT,
                fill=fill,
                outline=outline,
                width=width_outline,
                tags=("target", cell.name),
            )
            canvas.create_text(
                x + CELL_WIDTH / 2,
                row_y + CELL_HEIGHT / 2,
                text=str(cell.port),
                fill="white",
                font=("Segoe UI", 7, "bold"),
                tags=("target", cell.name),
            )
            item_ids[cell.name] = item
            x += CELL_WIDTH + CELL_GAP
        return row_y + CELL_HEIGHT + CELL_GAP

    def _on_source_click(self, event: tk.Event) -> None:
        name = self._hit_named_item(self.source_canvas, event, "source")
        if not name:
            return
        source_cell = next((cell for cell in self.source_cells if cell.name == name), None)
        if source_cell is None or not source_cell.placeable:
            self.selection_var.set(f"{name} is not a mappable source port.")
            return
        if self.selected_source == name:
            self.selected_source = None
            self.selection_var.set("Selection cleared. Click a source port.")
        else:
            self.selected_source = name
            self.selection_var.set(f"Selected source: {source_cell_detail(source_cell)}")
        self._draw_faceplates()

    def _on_target_click(self, event: tk.Event) -> None:
        name = self._hit_named_item(self.target_canvas, event, "target")
        if not name:
            return
        target_cell = next((cell for cell in self.target_cells if cell.name == name), None)
        if target_cell is None:
            return
        if self.selected_source is None:
            self.selection_var.set(
                f"{target_cell_detail(target_cell)}. Select a source port first."
            )
            return
        self.pairs = set_mapping(self.pairs, self.selected_source, name)
        self.selection_var.set(
            f"Mapped {self.selected_source} -> {name}. "
            f"{target_cell_detail(target_cell)}"
        )
        self.selected_source = None
        self._draw_faceplates()
        self._refresh_status()

    def _hit_named_item(self, canvas: tk.Canvas, event: tk.Event, kind: str) -> str | None:
        x = canvas.canvasx(event.x)
        y = canvas.canvasy(event.y)
        items = canvas.find_overlapping(x, y, x, y)
        for item in reversed(items):
            tags = canvas.gettags(item)
            if kind in tags and len(tags) >= 2:
                return tags[1]
        return None

    def _unmap_selected(self) -> None:
        if self.selected_source is None:
            self.selection_var.set("Select a mapped source port to unmap.")
            return
        self.pairs = clear_mapping(self.pairs, self.selected_source)
        self.selection_var.set(f"Unmapped {self.selected_source}.")
        self.selected_source = None
        self._draw_faceplates()
        self._refresh_status()

    def _clear_map(self) -> None:
        self.pairs = ()
        self.selected_source = None
        self.selection_var.set("Map cleared. Click a source port, then a target port.")
        self._draw_faceplates()
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = build_visual_mapping_status(
            self.source_cells,
            self.target_cells,
            self.pairs,
        )
        self.status_var.set(
            f"Mapped {status.mapped_count}. "
            f"Unmapped uplinks: {len(status.unmapped_uplink_sources)}. "
            f"Unmapped port-channel members: {len(status.unmapped_port_channel_members)}. "
            f"Collisions: {len(status.collision_targets)}. "
            f"PC members on uplink slots: {len(status.port_channel_on_uplink_slots)}."
        )
        self.warning_var.set(" ".join(status.warnings))

    def _apply(self) -> None:
        self.on_apply(self.pairs)
        self.top.destroy()
