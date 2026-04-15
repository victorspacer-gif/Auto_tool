"""Configuration serialization and deserialization."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import AppState, HotkeyJob


class ConfigSerializer:
    @staticmethod
    def to_dict(state: AppState) -> dict:
        jobs_data = [
            {
                "job_id": job.job_id,
                "key": job.key,
                "min_ms": job.min_ms,
                "max_ms": job.max_ms,
                "burst": job.burst_enabled,
                "burst_chance": job.burst_chance,
                "burst_cnt_min": job.burst_cnt_min,
                "burst_cnt_max": job.burst_cnt_max,
                "burst_int_ms": job.burst_int_ms,
                "use_focus": job.use_focus,
                "window_name": job.window_name,
                "restore_focus": job.restore_focus,
            }
            for job in state.jobs
        ]
        return {
            "jobs": jobs_data,
            "hotkey_bindings": dict(state.hotkey_bindings),
            "afk_min_ms": state.afk_min_ms,
            "afk_max_ms": state.afk_max_ms,
            "rclick_pos_x": state.rclick_pos[0],
            "rclick_pos_y": state.rclick_pos[1],
            "rclick_min_ms": state.rclick_min_ms,
            "rclick_max_ms": state.rclick_max_ms,
            "alarm_mp3": state.alarm_mp3,
            "alarm_threshold": state.alarm_threshold,
            "alarm_cooldown": state.alarm_cooldown,
            "alarm_auto_pause": state.alarm_auto_pause,
            "alarm_region": list(state.alarm_region) if state.alarm_region else None,
            "fish_rod_x": state.fish_rod_pos[0],
            "fish_rod_y": state.fish_rod_pos[1],
            "fish_spots": [[x, y] for x, y in state.fish_spots],
            "fish_cast_min_ms": state.fish_cast_min_ms,
            "fish_cast_max_ms": state.fish_cast_max_ms,
            "fish_wait_min_ms": state.fish_wait_min_ms,
            "fish_wait_max_ms": state.fish_wait_max_ms,
            "fish_rod_jitter": state.fish_rod_jitter,
            "fish_spot_jitter": state.fish_spot_jitter,
            "fish_session_minutes": state.fish_session_minutes,
            "rune_spell_key": state.rune_spell_key,
            "rune_cycle_delay_ms": state.rune_cycle_delay_ms,
            "rune_hand_x": state.rune_hand_pos[0],
            "rune_hand_y": state.rune_hand_pos[1],
            "rune_storage_x": state.rune_storage_pos[0],
            "rune_storage_y": state.rune_storage_pos[1],
            "rune_blank_x": state.rune_blank_pos[0],
            "rune_blank_y": state.rune_blank_pos[1],
            "rune_jitter": state.rune_jitter,
            "rune_cast_delay_ms": state.rune_cast_delay_ms,
        }

    @staticmethod
    def save_json(path: str, state: AppState) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(ConfigSerializer.to_dict(state), handle, indent=2)

    @staticmethod
    def save_xml(path: str, state: AppState) -> None:
        config = ConfigSerializer.to_dict(state)
        root = ET.Element("SystemMonitorConfig")
        jobs_el = ET.SubElement(root, "jobs")
        for job_data in config.pop("jobs", []):
            job_el = ET.SubElement(jobs_el, "job")
            for key, value in job_data.items():
                child = ET.SubElement(job_el, key)
                child.text = str(value)
        hotkeys_el = ET.SubElement(root, "hotkey_bindings")
        for key, value in config.pop("hotkey_bindings", {}).items():
            child = ET.SubElement(hotkeys_el, key)
            child.text = str(value)
        spots_el = ET.SubElement(root, "fish_spots")
        for x, y in config.pop("fish_spots", []):
            spot = ET.SubElement(spots_el, "spot")
            spot.text = f"{x},{y}"
        region = config.pop("alarm_region", None)
        region_el = ET.SubElement(root, "alarm_region")
        region_el.text = ",".join(map(str, region)) if region else ""
        for key, value in config.items():
            child = ET.SubElement(root, key)
            child.text = str(value)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def load_file(path: str) -> dict:
        target = Path(path)
        if target.suffix.lower() == ".xml":
            return ConfigSerializer._load_xml(path)
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        return {
            "cfg": {key: str(value) for key, value in raw.items() if key not in {"jobs", "fish_spots", "alarm_region", "hotkey_bindings"}},
            "jobs": raw.get("jobs", []),
            "spots": [tuple(item) for item in raw.get("fish_spots", [])],
            "alarm_region": tuple(raw["alarm_region"]) if raw.get("alarm_region") else None,
            "hotkeys": raw.get("hotkey_bindings", {}),
        }

    @staticmethod
    def _load_xml(path: str) -> dict:
        root = ET.parse(path).getroot()
        cfg: dict[str, str] = {}
        jobs: list[dict] = []
        spots: list[tuple[int, int]] = []
        alarm_region = None
        hotkeys: dict[str, str] = {}
        for child in root:
            if child.tag == "jobs":
                for job_el in child:
                    jobs.append({field.tag: field.text for field in job_el})
            elif child.tag == "fish_spots":
                for spot in child:
                    if spot.text:
                        x_val, y_val = spot.text.split(",")
                        spots.append((int(x_val), int(y_val)))
            elif child.tag == "alarm_region" and child.text:
                parts = child.text.split(",")
                if len(parts) == 4:
                    alarm_region = tuple(int(part) for part in parts)
            elif child.tag == "hotkey_bindings":
                hotkeys = {field.tag: field.text or "" for field in child}
            else:
                cfg[child.tag] = child.text or ""
        return {"cfg": cfg, "jobs": jobs, "spots": spots, "alarm_region": alarm_region, "hotkeys": hotkeys}

    @staticmethod
    def apply_loaded(state: AppState, payload: dict) -> None:
        cfg = payload["cfg"]
        jobs = payload["jobs"]
        spots = payload["spots"]
        alarm_region = payload["alarm_region"]
        hotkeys = payload["hotkeys"]

        def get_int(name: str, default: int) -> int:
            try:
                return int(float(cfg.get(name, default)))
            except (TypeError, ValueError):
                return default

        def get_float(name: str, default: float) -> float:
            try:
                return float(cfg.get(name, default))
            except (TypeError, ValueError):
                return default

        def get_str(name: str, default: str) -> str:
            return str(cfg.get(name, default))

        def get_bool(name: str, default: bool) -> bool:
            return str(cfg.get(name, str(default))).lower() == "true"

        state.afk_min_ms = get_int("afk_min_ms", state.afk_min_ms)
        state.afk_max_ms = get_int("afk_max_ms", state.afk_max_ms)
        state.rclick_pos = (
            get_int("rclick_pos_x", state.rclick_pos[0]),
            get_int("rclick_pos_y", state.rclick_pos[1]),
        )
        state.rclick_min_ms = get_int("rclick_min_ms", state.rclick_min_ms)
        state.rclick_max_ms = get_int("rclick_max_ms", state.rclick_max_ms)
        state.alarm_mp3 = get_str("alarm_mp3", state.alarm_mp3)
        state.alarm_threshold = get_float("alarm_threshold", state.alarm_threshold)
        state.alarm_cooldown = get_int("alarm_cooldown", state.alarm_cooldown)
        state.alarm_auto_pause = get_bool("alarm_auto_pause", state.alarm_auto_pause)
        state.alarm_region = alarm_region
        state.fish_rod_pos = (
            get_int("fish_rod_x", state.fish_rod_pos[0]),
            get_int("fish_rod_y", state.fish_rod_pos[1]),
        )
        state.fish_cast_min_ms = get_int("fish_cast_min_ms", state.fish_cast_min_ms)
        state.fish_cast_max_ms = get_int("fish_cast_max_ms", state.fish_cast_max_ms)
        state.fish_wait_min_ms = get_int("fish_wait_min_ms", state.fish_wait_min_ms)
        state.fish_wait_max_ms = get_int("fish_wait_max_ms", state.fish_wait_max_ms)
        state.fish_rod_jitter = get_int("fish_rod_jitter", state.fish_rod_jitter)
        state.fish_spot_jitter = get_int("fish_spot_jitter", state.fish_spot_jitter)
        state.fish_session_minutes = max(1, min(40, get_int("fish_session_minutes", state.fish_session_minutes)))
        state.fish_spots = list(spots)
        state.rune_spell_key = get_str("rune_spell_key", state.rune_spell_key)
        state.rune_cycle_delay_ms = get_int("rune_cycle_delay_ms", state.rune_cycle_delay_ms)
        state.rune_hand_pos = (
            get_int("rune_hand_x", state.rune_hand_pos[0]),
            get_int("rune_hand_y", state.rune_hand_pos[1]),
        )
        state.rune_storage_pos = (
            get_int("rune_storage_x", state.rune_storage_pos[0]),
            get_int("rune_storage_y", state.rune_storage_pos[1]),
        )
        state.rune_blank_pos = (
            get_int("rune_blank_x", state.rune_blank_pos[0]),
            get_int("rune_blank_y", state.rune_blank_pos[1]),
        )
        state.rune_jitter = get_int("rune_jitter", state.rune_jitter)
        state.rune_cast_delay_ms = get_int("rune_cast_delay_ms", state.rune_cast_delay_ms)

        for action, binding in hotkeys.items():
            if action in state.hotkey_bindings:
                state.hotkey_bindings[action] = binding

        state.jobs = []
        state.job_counter = 0
        for job_data in jobs:
            job = HotkeyJob(
                job_id=int(float(job_data.get("job_id", 0) or 0)) or len(state.jobs) + 1,
                key=job_data.get("key", "F1"),
                min_ms=int(float(job_data.get("min_ms", 1000))),
                max_ms=int(float(job_data.get("max_ms", 3000))),
                burst_enabled=str(job_data.get("burst", "false")).lower() == "true",
                burst_chance=float(job_data.get("burst_chance", 0.2)),
                burst_cnt_min=int(job_data.get("burst_cnt_min", 3)),
                burst_cnt_max=int(job_data.get("burst_cnt_max", 8)),
                burst_int_ms=int(job_data.get("burst_int_ms", 80)),
                use_focus=str(job_data.get("use_focus", "false")).lower() == "true",
                window_name=job_data.get("window_name", ""),
                restore_focus=str(job_data.get("restore_focus", "true")).lower() == "true",
            )
            state.jobs.append(job)
            state.job_counter = max(state.job_counter, job.job_id)
