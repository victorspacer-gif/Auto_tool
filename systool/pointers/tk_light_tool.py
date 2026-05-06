import tkinter as tk
from tkinter import messagebox

from .memory_backend import LightMemoryController, ProcessNotFoundError
from .pointer_reader import PointerReader
from .profiles import DEFAULT_LIGHT_PROFILE


class LightToolApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Light Effect Tool")
        self.geometry("460x220")
        self.resizable(False, False)

        self.process_name_var = tk.StringVar(value=DEFAULT_LIGHT_PROFILE.process_name)
        self.controller: LightMemoryController | None = None
        self.pointer_reader: PointerReader | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        tk.Label(self, text="Process name").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.process_name_var, width=28).grid(row=0, column=1, **pad)
        tk.Label(
            self,
            text="Uses Light Pointers.CT. Default = color 215 / intensity 8. Boosted = color 215 / intensity 11.",
            justify="left",
            wraplength=420,
        ).grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        tk.Button(self, text="Attach", width=16, command=self.attach).grid(row=2, column=0, **pad)
        tk.Button(self, text="Apply Default", width=16, command=self.apply_default).grid(row=2, column=1, **pad)
        tk.Button(self, text="Apply Boosted", width=16, command=self.apply_boosted).grid(row=3, column=0, columnspan=2, **pad)
        self.status = tk.Label(self, text="Ready", anchor="w")
        self.status.grid(row=4, column=0, columnspan=2, sticky="we", padx=12, pady=10)

    def attach(self) -> None:
        try:
            self.controller = LightMemoryController(self.process_name_var.get().strip())
            self.controller.attach()
            self.pointer_reader = PointerReader(self.controller)
            self.status.config(text="Attached successfully.")
        except ProcessNotFoundError as exc:
            messagebox.showerror("Attach failed", str(exc))

    def apply_boosted(self) -> None:
        self._apply(DEFAULT_LIGHT_PROFILE.color_enabled_value, DEFAULT_LIGHT_PROFILE.boosted_intensity_value)

    def apply_default(self) -> None:
        self._apply(DEFAULT_LIGHT_PROFILE.color_enabled_value, DEFAULT_LIGHT_PROFILE.default_intensity_value)

    def _apply(self, color_value: int, intensity_value: int) -> None:
        try:
            ctrl = self._require_controller()
            pointer_reader = self._require_pointer_reader()
            color_address, _intensity_address = pointer_reader.resolve_light_pair_addresses()
            result = ctrl.write_light_pair(color_address, color_value, intensity_value)
            self.status.config(
                text=(
                    f"Color 0x{result.color.address:X}: {result.color.old_value}->{result.color.new_value} | "
                    f"Intensity 0x{result.intensity.address:X}: {result.intensity.old_value}->{result.intensity.new_value}"
                )
            )
        except Exception as exc:
            messagebox.showerror("Patch failed", str(exc))

    def _require_controller(self) -> LightMemoryController:
        if self.controller is None:
            raise ProcessNotFoundError("Attach to process first.")
        return self.controller

    def _require_pointer_reader(self) -> PointerReader:
        if self.pointer_reader is None:
            raise ProcessNotFoundError("Attach to process first.")
        return self.pointer_reader


if __name__ == "__main__":
    app = LightToolApp()
    app.mainloop()
