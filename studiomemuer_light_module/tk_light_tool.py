import tkinter as tk
from tkinter import messagebox

from .light_profile import DEFAULT_PROFILE
from .memory_backend import LightMemoryController, ProcessNotFoundError


class LightToolApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Light Effect Tool")
        self.geometry("460x220")
        self.resizable(False, False)

        self.process_name_var = tk.StringVar(value=DEFAULT_PROFILE.process_name)

        self.controller: LightMemoryController | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        tk.Label(self, text="Process name").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.process_name_var, width=28).grid(row=0, column=1, **pad)

        tk.Label(
            self,
            text="Uses Light Pointers.CT. Default = color 215 / intensity 7. Boosted = color 215 / intensity 8.",
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
            self.status.config(text="Attached successfully.")
        except ProcessNotFoundError as exc:
            messagebox.showerror("Attach failed", str(exc))

    def apply_boosted(self) -> None:
        self._apply(DEFAULT_PROFILE.color_enabled_value, DEFAULT_PROFILE.boosted_intensity_value)

    def apply_default(self) -> None:
        self._apply(DEFAULT_PROFILE.color_enabled_value, DEFAULT_PROFILE.default_intensity_value)

    def _apply(self, color_value: int, intensity_value: int) -> None:
        try:
            ctrl = self._require_controller()
            result = ctrl.apply_light_pair_by_resolver(
                module_name=DEFAULT_PROFILE.module_name,
                pointer_chains=[list(chain) for chain in DEFAULT_PROFILE.pointer_chains],
                color_value=color_value,
                intensity_value=intensity_value,
                structure_value_offset=DEFAULT_PROFILE.structure_value_offset,
                signature_pattern=DEFAULT_PROFILE.signature_pattern,
                signature_offset_to_base=DEFAULT_PROFILE.signature_offset_to_base,
            )
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


if __name__ == "__main__":
    app = LightToolApp()
    app.mainloop()
