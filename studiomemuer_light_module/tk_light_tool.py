import tkinter as tk
from tkinter import messagebox

from .light_profile import DEFAULT_PROFILE
from .memory_backend import LightMemoryController, ProcessNotFoundError, MemoryWriteError


class LightToolApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Light Effect Tool")
        self.geometry("460x260")
        self.resizable(False, False)

        self.process_name_var = tk.StringVar(value=DEFAULT_PROFILE.process_name)
        self.address_var = tk.StringVar(value=DEFAULT_PROFILE.address_hex)
        self.default_value_var = tk.StringVar(value=DEFAULT_PROFILE.default_value_hex)
        self.boosted_value_var = tk.StringVar(value=DEFAULT_PROFILE.boosted_value_hex)

        self.controller: LightMemoryController | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        tk.Label(self, text="Process name").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.process_name_var, width=28).grid(row=0, column=1, **pad)

        tk.Label(self, text="Address (hex)").grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.address_var, width=28).grid(row=1, column=1, **pad)

        tk.Label(self, text="Default value (hex)").grid(row=2, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.default_value_var, width=28).grid(row=2, column=1, **pad)

        tk.Label(self, text="Boosted value (hex)").grid(row=3, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.boosted_value_var, width=28).grid(row=3, column=1, **pad)

        tk.Button(self, text="Attach", width=16, command=self.attach).grid(row=4, column=0, **pad)
        tk.Button(self, text="Read Current Byte", width=16, command=self.read_current).grid(row=4, column=1, **pad)
        tk.Button(self, text="Apply Boosted", width=16, command=self.apply_boosted).grid(row=5, column=0, **pad)
        tk.Button(self, text="Apply Default", width=16, command=self.apply_default).grid(row=5, column=1, **pad)

        self.status = tk.Label(self, text="Ready", anchor="w")
        self.status.grid(row=6, column=0, columnspan=2, sticky="we", padx=12, pady=10)

    def attach(self) -> None:
        try:
            self.controller = LightMemoryController(self.process_name_var.get().strip())
            self.controller.attach()
            self.status.config(text="Attached successfully.")
        except ProcessNotFoundError as exc:
            messagebox.showerror("Attach failed", str(exc))

    def read_current(self) -> None:
        try:
            ctrl = self._require_controller()
            value = ctrl.read_byte(int(self.address_var.get().strip(), 16))
            self.status.config(text=f"Current byte: 0x{value:02X}")
        except (ValueError, ProcessNotFoundError, MemoryWriteError) as exc:
            messagebox.showerror("Read failed", str(exc))

    def apply_boosted(self) -> None:
        self._apply(self.boosted_value_var.get().strip())

    def apply_default(self) -> None:
        self._apply(self.default_value_var.get().strip())

    def _apply(self, value_hex: str) -> None:
        try:
            ctrl = self._require_controller()
            result = ctrl.apply_light_value(self.address_var.get().strip(), value_hex)
            self.status.config(
                text=f"Patched 0x{result.address:X}: 0x{result.old_value:02X} -> 0x{result.new_value:02X}"
            )
        except (ValueError, ProcessNotFoundError, MemoryWriteError) as exc:
            messagebox.showerror("Patch failed", str(exc))

    def _require_controller(self) -> LightMemoryController:
        if self.controller is None:
            raise ProcessNotFoundError("Attach to process first.")
        return self.controller


if __name__ == "__main__":
    app = LightToolApp()
    app.mainloop()
