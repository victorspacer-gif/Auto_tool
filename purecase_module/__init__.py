import sys
from pathlib import Path

# Handle direct execution: ensure package context for relative imports
if __package__ is None or __name__ == "__main__":
    package_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(package_root))
    from purecase_module.runtime import (
        PureCaseInstallation,
        build_start_command,
        configure_box,
        ensure_box,
        find_installation,
        launch_in_box,
        list_box_pids,
        reload_configuration,
        sanitize_box_name,
        terminate_box,
        create_job_object,
        get_safer_token,
        build_spoofed_env,
        launch_with_job_object,
    )
else:
    from .runtime import (
        PureCaseInstallation,
        build_start_command,
        configure_box,
        ensure_box,
        find_installation,
        launch_in_box,
        list_box_pids,
        reload_configuration,
        sanitize_box_name,
        terminate_box,
        create_job_object,
        get_safer_token,
        build_spoofed_env,
        launch_with_job_object,
    )

__all__ = [
    "PureCaseInstallation",
    "build_start_command",
    "configure_box",
    "ensure_box",
    "find_installation",
    "launch_in_box",
    "list_box_pids",
    "reload_configuration",
    "sanitize_box_name",
    "terminate_box",
    "create_job_object",
    "get_safer_token",
    "build_spoofed_env",
    "launch_with_job_object",
]
