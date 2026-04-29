"""Unified magic-number scanner, JSON exporter, and Tkinter editor."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tkinter as tk
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_ROOT / "systool" / "config.py"
CONSTANTS_FILE = PROJECT_ROOT / "systool" / "constants.py"
REPORT_FILE = PROJECT_ROOT / "magic_number_report.json"
IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    "vendor",
}
IGNORED_FILES = {
    "magic_number_tool.py",
}
KEYWORD_HINTS = (
    "alarm",
    "bonus",
    "buffer",
    "cap",
    "chance",
    "click",
    "cooldown",
    "delay",
    "duration",
    "freeze",
    "food",
    "healer",
    "interval",
    "jitter",
    "mana",
    "mouse",
    "pause",
    "poll",
    "press",
    "retry",
    "rune",
    "sample",
    "scale",
    "session",
    "settle",
    "speed",
    "threshold",
    "timeout",
    "volume",
    "wait",
)
SAFE_LITERAL_TYPES = (int, float)


@dataclass
class MagicNumberFinding:
    file_path: str
    class_name: str
    variable_name: str
    value: int | float
    value_type: str
    line_number: int
    category: str
    confidence: float
    context: str
    editable: bool = False
    unsafe_edit: bool = False

    @property
    def display_name(self) -> str:
        if self.class_name == "module_level":
            return self.variable_name
        return f"{self.class_name}.{self.variable_name}"

    @property
    def identifier_key(self) -> tuple[str, str, str]:
        return (self.file_path, self.class_name, self.variable_name)

    def to_report(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "class_name": self.class_name,
            "variable_name": self.variable_name,
            "value": self.value,
            "type": self.value_type,
            "line_number": self.line_number,
        }


@dataclass
class EditableAssignment:
    file_path: Path
    class_name: str
    variable_name: str
    value: int | float
    value_type: type[int] | type[float]
    line_no: int
    col_start: int
    col_end: int
    category: str
    unsafe: bool = False

    @property
    def identifier_key(self) -> tuple[str, str, str]:
        return (self.file_path.as_posix(), self.class_name, self.variable_name)

    @property
    def display_name(self) -> str:
        if self.class_name == "module_level":
            return self.variable_name
        return f"{self.class_name}.{self.variable_name}"


class _ParentAwareVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, source: str, include_unsafe_editable: bool = False) -> None:
        self.path = path
        self.lines = source.splitlines()
        self.parents: dict[ast.AST, ast.AST] = {}
        self.findings: list[MagicNumberFinding] = []
        self.editable_assignments: list[EditableAssignment] = []
        self.include_unsafe_editable = include_unsafe_editable

    def visit(self, node: ast.AST) -> Any:
        for child in ast.iter_child_nodes(node):
            self.parents[child] = node
        return super().visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        self._collect_assignment(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        self._collect_assignment(node)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, bool) or not isinstance(node.value, SAFE_LITERAL_TYPES):
            return
        parent = self.parents.get(node)
        if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.USub):
            return
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and getattr(parent, "value", None) is node:
            return
        self._collect_literal(node)

    def _collect_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        is_safe_assignment = self.path in {CONFIG_FILE, CONSTANTS_FILE}
        is_unsafe_assignment = (
            self.include_unsafe_editable
            and not is_safe_assignment
            and self._supports_unsafe_edit(node)
        )
        if not is_safe_assignment and not is_unsafe_assignment:
            return
        target: ast.expr | None
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                return
            target = node.targets[0]
            value = node.value
        else:
            target = node.target
            value = node.value
        if not isinstance(target, ast.Name) or value is None:
            return
        if not isinstance(value, ast.Constant) or isinstance(value.value, bool) or not isinstance(value.value, SAFE_LITERAL_TYPES):
            return

        category = self._classify_assignment_category(value)
        is_unsafe = not is_safe_assignment
        class_name = self._owner_class_name(node)
        value_type = "float" if isinstance(value.value, float) else "int"
        self.editable_assignments.append(
            EditableAssignment(
                file_path=self.path,
                class_name=class_name,
                variable_name=target.id,
                value=value.value,
                value_type=float if isinstance(value.value, float) else int,
                line_no=value.lineno,
                col_start=value.col_offset,
                col_end=value.end_col_offset or value.col_offset,
                category=category,
                unsafe=is_unsafe,
            )
        )
        self.findings.append(
            MagicNumberFinding(
                file_path=self.path.as_posix(),
                class_name=class_name,
                variable_name=target.id,
                value=value.value,
                value_type=value_type,
                line_number=value.lineno,
                category=category,
                confidence=0.99,
                context=self._line_text(value.lineno),
                editable=True,
                unsafe_edit=is_unsafe,
            )
        )

    def _collect_literal(self, node: ast.Constant) -> None:
        category, confidence = self._classify_literal(node)
        if category == "DERIVED" and confidence < 0.75:
            return
        value_type = "float" if isinstance(node.value, float) else "int"
        self.findings.append(
            MagicNumberFinding(
                file_path=self.path.as_posix(),
                class_name=self._owner_class_name(node),
                variable_name=self._suggest_name(node),
                value=node.value,
                value_type=value_type,
                line_number=node.lineno,
                category=category,
                confidence=confidence,
                context=self._line_text(node.lineno),
            )
        )

    def _classify_literal(self, node: ast.Constant) -> tuple[str, float]:
        line = self._line_text(node.lineno).lower()
        parent = self.parents.get(node)
        path_text = self.path.as_posix()

        if self.path in {CONFIG_FILE, CONSTANTS_FILE}:
            return ("DEFAULT_CONFIG" if self.path == CONFIG_FILE else "CONSTANT", 0.99)
        if "/tests/" in path_text or path_text.endswith(".spec.py"):
            return ("DERIVED", 0.6)
        if self._inside_enum(node):
            return ("DERIVED", 0.95)
        if self._in_range_or_index(node):
            return ("DERIVED", 0.85)
        if isinstance(parent, ast.Compare):
            if any(hint in line for hint in KEYWORD_HINTS):
                return ("DEFAULT_CONFIG", 0.82)
            return ("DERIVED", 0.7)
        if isinstance(parent, ast.Call):
            func_name = self._call_name(parent.func)
            if func_name in {"sleep", "wait", "wait_interruptible", "randint", "uniform"}:
                return ("CONSTANT", 0.8)
            if func_name in {"max", "min"} and any(hint in line for hint in KEYWORD_HINTS):
                return ("DEFAULT_CONFIG", 0.84)
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            return ("DEFAULT_CONFIG" if "models.py" in path_text else "CONSTANT", 0.85)
        if any(hint in line for hint in KEYWORD_HINTS):
            if any(part in path_text for part in ("/ui/", "/config.py", "/models.py")):
                return ("DEFAULT_CONFIG", 0.78)
            return ("CONSTANT", 0.76)
        return ("DERIVED", 0.7)

    def _inside_enum(self, node: ast.AST) -> bool:
        current = self.parents.get(node)
        while current is not None:
            if isinstance(current, ast.ClassDef):
                for base in current.bases:
                    if self._call_name(base) == "Enum":
                        return True
            current = self.parents.get(current)
        return False

    def _supports_unsafe_edit(self, node: ast.Assign | ast.AnnAssign) -> bool:
        path_text = self.path.as_posix()
        if "/tests/" in path_text or path_text.endswith(".spec.py"):
            return False
        if self.path.name == "magic_number_report.json":
            return False
        parent = self.parents.get(node)
        if not isinstance(parent, (ast.Module, ast.ClassDef)):
            return False
        if isinstance(parent, ast.ClassDef):
            for base in parent.bases:
                if self._call_name(base) == "Enum":
                    return False
        return True

    def _classify_assignment_category(self, value_node: ast.Constant) -> str:
        if self.path == CONFIG_FILE:
            return "DEFAULT_CONFIG"
        if self.path == CONSTANTS_FILE:
            return "CONSTANT"
        category, _confidence = self._classify_literal(value_node)
        return category

    def _in_range_or_index(self, node: ast.Constant) -> bool:
        current = self.parents.get(node)
        while current is not None:
            if isinstance(current, ast.Subscript) and current.slice is node:
                return True
            if isinstance(current, ast.Call) and self._call_name(current.func) == "range":
                return True
            current = self.parents.get(current)
        return False

    def _suggest_name(self, node: ast.Constant) -> str:
        line = re.sub(r"[^A-Za-z0-9_]+", "_", self._line_text(node.lineno).strip()).strip("_")
        stem = self.path.stem.upper()
        if line:
            words = [part for part in line.upper().split("_") if part and not part.isdigit()]
            candidate = "_".join(words[:6])
            if candidate:
                return f"{stem}_{candidate}"
        value_text = str(node.value).replace(".", "_").replace("-", "NEG_")
        return f"{stem}_VALUE_{value_text}"

    def _call_name(self, func: ast.expr) -> str:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return ""

    def _owner_class_name(self, node: ast.AST) -> str:
        current = self.parents.get(node)
        while current is not None:
            if isinstance(current, ast.ClassDef):
                return current.name
            current = self.parents.get(current)
        return "module_level"

    def _line_text(self, line_no: int) -> str:
        return self.lines[line_no - 1] if 0 < line_no <= len(self.lines) else ""


def iter_python_files(root: Path = PROJECT_ROOT) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.name in IGNORED_FILES:
            continue
        files.append(path)
    return sorted(files)


def scan_project(
    root: Path = PROJECT_ROOT,
    include_unsafe_editable: bool = False,
) -> tuple[list[MagicNumberFinding], list[EditableAssignment]]:
    findings: list[MagicNumberFinding] = []
    editable: list[EditableAssignment] = []
    for path in iter_python_files(root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path.as_posix())
        visitor = _ParentAwareVisitor(path, source, include_unsafe_editable=include_unsafe_editable)
        visitor.visit(tree)
        findings.extend(visitor.findings)
        editable.extend(visitor.editable_assignments)
    findings.sort(key=lambda item: (item.file_path, item.class_name, item.line_number, item.variable_name))
    editable.sort(key=lambda item: (item.unsafe, item.file_path.as_posix(), item.class_name, item.category, item.variable_name))
    return findings, editable


def write_report(path: Path = REPORT_FILE, findings: list[MagicNumberFinding] | None = None) -> Path:
    findings = findings if findings is not None else scan_project()[0]
    path.write_text(json.dumps([item.to_report() for item in findings], indent=2), encoding="utf-8")
    return path


def parse_numeric_value(raw: str, expected_type: type[int] | type[float]) -> int | float:
    text = raw.strip()
    if not text:
        raise ValueError("Value cannot be empty.")
    if expected_type is int:
        if re.search(r"[.eE]", text):
            raise ValueError("Expected an integer.")
        return int(text)
    return float(text)


def apply_assignment_updates(
    updates: dict[tuple[str, str, str], int | float],
    dry_run: bool = False,
    include_unsafe_editable: bool = False,
) -> dict[str, list[str]]:
    _findings, editable = scan_project(include_unsafe_editable=include_unsafe_editable)
    editable_map = {item.identifier_key: item for item in editable}
    file_changes: dict[Path, list[EditableAssignment]] = {}
    for key, value in updates.items():
        assignment = editable_map.get(key)
        if assignment is None:
            raise KeyError(f"Unknown editable assignment: {key}")
        assignment.value = value
        file_changes.setdefault(assignment.file_path, []).append(assignment)

    preview: dict[str, list[str]] = {}
    for file_path, assignments in file_changes.items():
        original_text = file_path.read_text(encoding="utf-8")
        lines = original_text.splitlines(keepends=True)
        for assignment in sorted(assignments, key=lambda item: item.line_no, reverse=True):
            line = lines[assignment.line_no - 1]
            replacement = repr(float(assignment.value)) if assignment.value_type is float else repr(int(assignment.value))
            updated = line[:assignment.col_start] + replacement + line[assignment.col_end:]
            preview.setdefault(file_path.as_posix(), []).append(updated.rstrip("\n"))
            lines[assignment.line_no - 1] = updated
        if dry_run:
            continue
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = file_path.with_suffix(file_path.suffix + f".{timestamp}.bak")
        backup.write_text(original_text, encoding="utf-8")
        file_path.write_text("".join(lines), encoding="utf-8")
    return preview


def scan_summary(findings: list[MagicNumberFinding]) -> dict[str, int]:
    return dict(sorted(Counter(item.category for item in findings).items()))


class MagicNumberEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Magic Number Tool")
        self.geometry("1280x780")
        self.minsize(1040, 620)

        self.findings: list[MagicNumberFinding] = []
        self.editable: list[EditableAssignment] = []
        self.filter_var = tk.StringVar()
        self.include_unsafe_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.summary_var = tk.StringVar(value="")
        self.change_vars: dict[tuple[str, str, str], tk.StringVar] = {}
        self.original_values: dict[tuple[str, str, str], str] = {}
        self.value_types: dict[tuple[str, str, str], type[int] | type[float]] = {}
        self._search_after_id: str | None = None

        self._build()
        self.reload()

    def _build(self) -> None:
        toolbar = tk.Frame(self, padx=12, pady=10)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="Search").pack(side="left")
        entry = tk.Entry(toolbar, textvariable=self.filter_var, width=44)
        entry.pack(side="left", padx=(8, 12))
        entry.bind("<KeyRelease>", lambda _event: self._schedule_filter_refresh())
        tk.Checkbutton(
            toolbar,
            text="Load unsafe editable values",
            variable=self.include_unsafe_var,
            command=self.reload,
        ).pack(side="left", padx=(0, 12))
        ttk.Button(toolbar, text="Reload Scan", command=self.reload).pack(side="left")
        ttk.Button(toolbar, text="Generate Report", command=self.generate_report).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Export JSON", command=self.export_report).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Preview Save", command=self.preview_save).pack(side="left")
        ttk.Button(toolbar, text="Save Changes", command=self.save_changes).pack(side="left", padx=(8, 0))

        summary = tk.Label(self, textvariable=self.summary_var, anchor="w", padx=12)
        summary.pack(fill="x")

        findings_frame = tk.LabelFrame(self, text="Detected Values", padx=8, pady=8)
        findings_frame.pack(fill="both", expand=True, padx=12, pady=(8, 10))

        columns = ("category", "name", "value", "type", "current", "origin", "line", "confidence", "edit_mode")
        self.tree = ttk.Treeview(findings_frame, columns=columns, show="headings")
        widths = {
            "category": 130,
            "name": 250,
            "value": 100,
            "type": 70,
            "current": 110,
            "origin": 360,
            "line": 60,
            "confidence": 90,
            "edit_mode": 100,
        }
        for column in columns:
            self.tree.heading(column, text=column.title())
            self.tree.column(column, width=widths[column], anchor="w")
        findings_scroll = ttk.Scrollbar(findings_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=findings_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        findings_scroll.pack(side="right", fill="y")

        editor = tk.LabelFrame(self, text="Editable Centralized Values", padx=12, pady=10)
        editor.pack(fill="both", expand=False, padx=12, pady=(0, 10))
        self.editor_canvas = tk.Canvas(editor, height=250)
        self.editor_scroll = ttk.Scrollbar(editor, orient="vertical", command=self.editor_canvas.yview)
        self.editor_frame = tk.Frame(self.editor_canvas)
        self.editor_frame.bind(
            "<Configure>",
            lambda _event: self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all")),
        )
        self.editor_canvas.create_window((0, 0), window=self.editor_frame, anchor="nw")
        self.editor_canvas.configure(yscrollcommand=self.editor_scroll.set)
        self.editor_canvas.pack(side="left", fill="both", expand=True)
        self.editor_scroll.pack(side="right", fill="y")

        status = tk.Label(self, textvariable=self.status_var, anchor="w", padx=12, pady=8)
        status.pack(fill="x")

    def reload(self) -> None:
        self.findings, self.editable = scan_project(include_unsafe_editable=self.include_unsafe_var.get())
        self.original_values.clear()
        self.change_vars.clear()
        self.value_types.clear()
        for item in self.editable:
            key = item.identifier_key
            self.original_values[key] = str(item.value)
            self.change_vars[key] = tk.StringVar(value=str(item.value))
            self.value_types[key] = item.value_type
        self._refresh_views()
        summary = scan_summary(self.findings)
        self.summary_var.set(
            " | ".join(
                [
                    f"Findings: {len(self.findings)}",
                    f"Editable: {len(self.editable)}",
                    f"Unsafe loaded: {'yes' if self.include_unsafe_var.get() else 'no'}",
                    *(f"{name}: {count}" for name, count in summary.items()),
                ]
            )
        )
        self.status_var.set("Scan complete.")

    def generate_report(self) -> None:
        self.reload()
        path = write_report(REPORT_FILE, self.findings)
        self.status_var.set(f"Report generated at {path}")
        messagebox.showinfo("Report generated", f"Regenerated report and refreshed the UI:\n{path}")

    def export_report(self) -> None:
        path = write_report(REPORT_FILE, self.findings)
        self.status_var.set(f"Report exported to {path}")
        messagebox.showinfo("Report exported", f"Wrote {len(self.findings)} findings to:\n{path}")

    def _matches_query(self, *parts: object) -> bool:
        query = self.filter_var.get().strip().lower()
        if not query:
            return True
        haystack = " ".join(str(part) for part in parts).lower()
        return query in haystack

    def _schedule_filter_refresh(self) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(120, self._apply_filter_refresh)

    def _apply_filter_refresh(self) -> None:
        self._search_after_id = None
        self._refresh_views()

    def _refresh_views(self) -> None:
        self.render_rows()
        self.render_editor()

    def render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for finding in self.findings:
            current = ""
            if finding.editable:
                var = self.change_vars.get(finding.identifier_key)
                current = var.get() if var else ""
            if not self._matches_query(
                finding.category,
                finding.display_name,
                finding.value,
                finding.value_type,
                current,
                finding.file_path,
                finding.class_name,
                finding.context,
                "unsafe" if finding.unsafe_edit else "safe",
            ):
                continue
            self.tree.insert(
                "",
                "end",
                values=(
                    finding.category,
                    finding.display_name,
                    finding.value,
                    finding.value_type,
                    current,
                    finding.file_path,
                    finding.line_number,
                    f"{finding.confidence:.2f}",
                    "unsafe" if finding.unsafe_edit else "safe",
                ),
            )

    def render_editor(self) -> None:
        for child in self.editor_frame.winfo_children():
            child.destroy()

        grouped: dict[str, list[EditableAssignment]] = defaultdict(list)
        for item in self.editable:
            key = item.identifier_key
            current = self.change_vars[key].get()
            if not self._matches_query(
                item.category,
                item.display_name,
                item.variable_name,
                item.class_name,
                item.value,
                current,
                item.file_path.name,
                item.file_path.as_posix(),
            ):
                continue
            grouped[item.category].append(item)

        row = 0
        for unsafe_mode in (False, True):
            if unsafe_mode and not self.include_unsafe_var.get():
                continue
            for category in ("DEFAULT_CONFIG", "CONSTANT", "DERIVED"):
                items = [
                    item for item in grouped.get(category, [])
                    if item.unsafe == unsafe_mode
                ]
                if not items:
                    continue
                label = f"{category} ({len(items)})"
                if unsafe_mode:
                    label = f"{label} [unsafe]"
                tk.Label(
                    self.editor_frame,
                    text=label,
                    font=("Segoe UI", 10, "bold"),
                ).grid(row=row, column=0, sticky="w", pady=(0, 6))
                row += 1
                for item in items:
                    key = item.identifier_key
                    tk.Label(self.editor_frame, text=item.display_name, width=38, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
                    tk.Entry(self.editor_frame, textvariable=self.change_vars[key], width=16).grid(row=row, column=1, sticky="w", padx=(0, 8), pady=2)
                    tk.Label(self.editor_frame, text=f"{item.file_path.name}:{item.line_no}", width=26, anchor="w").grid(row=row, column=2, sticky="w", pady=2)
                    tk.Label(self.editor_frame, text=f"Original: {self.original_values[key]}", width=20, anchor="w").grid(row=row, column=3, sticky="w", pady=2)
                    tk.Label(self.editor_frame, text="unsafe" if item.unsafe else "safe", width=10, anchor="w").grid(row=row, column=4, sticky="w", pady=2)
                    row += 1
        if row == 0:
            tk.Label(self.editor_frame, text="No editable values match the current search.").grid(row=0, column=0, sticky="w")

    def _collect_updates(self) -> dict[tuple[str, str, str], int | float]:
        updates: dict[tuple[str, str, str], int | float] = {}
        for key, variable in self.change_vars.items():
            original = self.original_values[key]
            if variable.get().strip() == original:
                continue
            updates[key] = parse_numeric_value(variable.get(), self.value_types[key])
        return updates

    def preview_save(self) -> None:
        try:
            updates = self._collect_updates()
            if not updates:
                self.status_var.set("No pending changes.")
                return
            preview = apply_assignment_updates(
                updates,
                dry_run=True,
                include_unsafe_editable=self.include_unsafe_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))
            return

        lines: list[str] = []
        for file_name, updated_lines in preview.items():
            lines.append(file_name)
            lines.extend(f"  {line}" for line in updated_lines)
        messagebox.showinfo("Dry Run Preview", "\n".join(lines[:80]))
        self.status_var.set(f"Previewed {len(updates)} change(s) without writing files.")

    def save_changes(self) -> None:
        try:
            updates = self._collect_updates()
            if not updates:
                self.status_var.set("No changes to save.")
                return
            apply_assignment_updates(
                updates,
                dry_run=False,
                include_unsafe_editable=self.include_unsafe_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return

        self.reload()
        self.status_var.set(f"Saved {len(updates)} change(s). Timestamped backups were created first.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Project root to scan.")
    parser.add_argument("--output", type=Path, default=REPORT_FILE, help="Where to write the JSON report.")
    parser.add_argument("--dry-run", action="store_true", help="Print a scan summary instead of writing the report.")
    parser.add_argument("--ui", action="store_true", help="Launch the Tkinter editor.")
    parser.add_argument("--unsafe", action="store_true", help="Include unsafe editable assignments outside centralized config/constants.")
    return parser


def run_cli(root: Path, output: Path, dry_run: bool, include_unsafe_editable: bool) -> int:
    findings, editable = scan_project(root, include_unsafe_editable=include_unsafe_editable)
    if dry_run:
        summary = scan_summary(findings)
        print("Magic number scan summary:")
        for category, count in summary.items():
            print(f"  {category}: {count}")
        print(f"  editable: {len(editable)}")
        print(f"  unsafe_loaded: {'yes' if include_unsafe_editable else 'no'}")
        print(f"  total: {len(findings)}")
        return 0
    path = write_report(output, findings)
    print(f"Wrote {len(findings)} findings to {path}")
    print(f"Editable centralized values: {len(editable)}")
    print(f"Unsafe editable values loaded: {'yes' if include_unsafe_editable else 'no'}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.ui or len(sys.argv) == 1:
        app = MagicNumberEditor()
        app.include_unsafe_var.set(bool(args.unsafe))
        app.reload()
        app.mainloop()
        return 0
    return run_cli(args.root, args.output, args.dry_run, args.unsafe)


if __name__ == "__main__":
    raise SystemExit(main())
