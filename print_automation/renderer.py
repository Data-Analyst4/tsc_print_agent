from __future__ import annotations

from pathlib import Path

import pdf2tspl as core_converter

from .config import TemplateProfile


def _fmt_mm(value: float) -> str:
    out = f"{value:.3f}".rstrip("0").rstrip(".")
    return out if out else "0"


def _inject_setup_commands(tspl: bytes, profile: TemplateProfile) -> bytes:
    commands: list[str] = []

    sensor = profile.sensor.lower()
    if sensor == "gap":
        commands.append(f"GAP {_fmt_mm(profile.gap_mm)} mm,{_fmt_mm(profile.gap_offset_mm)} mm")
    elif sensor == "continuous":
        commands.append("GAP 0,0")

    commands.append(f"DIRECTION {profile.direction}")
    commands.append(f"REFERENCE {profile.reference_x},{profile.reference_y}")

    if profile.speed is not None:
        commands.append(f"SPEED {profile.speed}")
    if profile.density is not None:
        commands.append(f"DENSITY {profile.density}")

    if not commands:
        return tspl

    marker = b"\r\nCLS\r\n"
    if marker not in tspl:
        return tspl
    injected = ("\r\n" + "\r\n".join(commands)).encode("ascii")
    return tspl.replace(marker, injected + marker, 1)


def render_pdf_to_tspl(pdf_path: Path, profile: TemplateProfile) -> bytes:
    tspl = core_converter.pdf2tspl(
        str(pdf_path),
        labelwidth_mm=profile.label_width_mm,
        labelheight_mm=profile.label_height_mm,
        dpi=profile.dpi,
        rotate=profile.rotate,
        x_offset_dots=profile.x_offset_dots,
        y_offset_dots=profile.y_offset_dots,
    )
    return _inject_setup_commands(tspl, profile)

