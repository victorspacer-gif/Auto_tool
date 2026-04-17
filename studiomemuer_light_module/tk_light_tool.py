from studiomemuer_light_module.memory_backend import (
    AddressResolveError,
    LightMemoryController,
    MemoryWriteError,
    ProcessNotFoundError,
)

from studiomemuer_light_module.light_profile import DEFAULT_PROFILE


def test_light_toggle():
    controller = LightMemoryController(DEFAULT_PROFILE.process_name)

    try:
        print("[INFO] Attaching to process...")
        controller.attach()

        print("[INFO] Resolving dynamic target address...")
        address = controller.resolve_light_address(
            module_name=DEFAULT_PROFILE.module_name,
            pointer_chains=DEFAULT_PROFILE.pointer_chains,
            structure_value_offset=DEFAULT_PROFILE.structure_value_offset,
            signature_pattern=DEFAULT_PROFILE.signature_pattern,
            signature_offset_to_base=DEFAULT_PROFILE.signature_offset_to_base,
        )

        print(f"[INFO] Final resolved address: 0x{address:X}")

        print("[INFO] Writing boosted light value...")
        result = controller.apply_light_value(
            module_name=DEFAULT_PROFILE.module_name,
            pointer_chains=DEFAULT_PROFILE.pointer_chains,
            structure_value_offset=DEFAULT_PROFILE.structure_value_offset,
            value_hex=DEFAULT_PROFILE.boosted_value_hex,
            signature_pattern=DEFAULT_PROFILE.signature_pattern,
            signature_offset_to_base=DEFAULT_PROFILE.signature_offset_to_base,
        )

        print(f"[SUCCESS] Patched: {result}")

    except ProcessNotFoundError as e:
        print(f"[ERROR] {e}")

    except MemoryWriteError as e:
        print(f"[ERROR] {e}")

    except AddressResolveError as e:
        print(f"[ERROR] {e}")

    finally:
        controller.detach()
        print("[INFO] Detached.")


if __name__ == "__main__":
    test_light_toggle()