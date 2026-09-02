from __future__ import annotations

import sys
from pathlib import Path


def create_icon() -> Path:
    assets_dir = Path(__file__).resolve().parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    icon_path = assets_dir / "icon.ico"

    try:
        from PIL import Image, ImageDraw

        size = 256
        image = Image.new("RGBA", (size, size), (10, 12, 24, 255))
        draw = ImageDraw.Draw(image)

        for i in range(0, size, 18):
            draw.line((i, 0, i, size), fill=(34, 211, 238, 120), width=1)
            draw.line((0, i, size, i), fill=(34, 211, 238, 100), width=1)

        for x0, y0, x1, y1, color in [
            (36, 36, 220, 220, (34, 211, 238, 255)),
            (36, 220, 220, 36, (236, 72, 153, 255)),
            (176, 86, 176, 170, (168, 85, 247, 255)),
        ]:
            draw.line((x0, y0, x1, y1), fill=color, width=10)

        draw.rounded_rectangle((48, 48, 208, 208), radius=28, outline=(0, 255, 255, 255), width=6)
        draw.text((94, 100), "PR", fill=(255, 255, 255, 255), font=None)
        image.save(icon_path, format="ICO")
        return icon_path
    except Exception:
        fallback = assets_dir / "icon.png"
        fallback.write_text("cyberpunk-fallback", encoding="utf-8")
        return fallback


def create_shortcut() -> Path:
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    target = (Path(__file__).resolve().parent / "start_app.bat").resolve()
    icon_path = create_icon()
    shortcut_path = desktop / "Paper Repro Runner.lnk"

    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(target)
        shortcut.WorkingDirectory = str(target.parent)
        shortcut.IconLocation = str(icon_path)
        shortcut.save()
    except Exception:
        shortcut_path = desktop / "Paper Repro Runner.cmd"
        shortcut_path.write_text(
            f'@echo off\ncd /d "{target.parent}"\ncall "{target}"\n',
            encoding="utf-8",
        )

    return shortcut_path


if __name__ == "__main__":
    result = create_shortcut()
    print(f"Desktop shortcut created: {result}")
