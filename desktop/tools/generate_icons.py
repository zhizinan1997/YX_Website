"""生成桌面客户端所需的应用图标与托盘图标。

Tauri 打包 Windows 安装包需要 `icon.ico` 与一组 PNG；托盘角标另需两枚小尺寸
PNG（正常 / 有未读）。这里用 Pillow 按后台的品牌配色直接绘制，避免引入设计资源
依赖，也让图标可以随品牌调整重新生成。

用法（项目根目录）：
    python desktop/tools/generate_icons.py

产物：
    desktop/src-tauri/icons/32x32.png
    desktop/src-tauri/icons/128x128.png
    desktop/src-tauri/icons/128x128@2x.png
    desktop/src-tauri/icons/icon.png
    desktop/src-tauri/icons/icon.ico
    desktop/src-tauri/icons/tray.png
    desktop/src-tauri/icons/tray-unread.png

作者：元芯传感技术团队
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# 与 admin/styles/tokens.css 保持一致的品牌配色。
NAVY_DEEP = (8, 25, 45)
NAVY_PRIMARY = (18, 61, 113)
ACCENT = (39, 199, 217)
UNREAD = (200, 70, 88)
WHITE = (255, 255, 255)

ICON_DIR = Path(__file__).resolve().parent.parent / "src-tauri" / "icons"

# 先在 1024px 上绘制再降采样，边缘比直接画小图干净得多。
CANVAS = 1024
CORNER_RADIUS_RATIO = 0.22
STROKE_RATIO = 0.115
DIAGONAL_JOIN_RATIO = 0.56


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """生成竖直渐变底。"""
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        ratio = y / max(1, size - 1)
        gradient.putpixel(
            (0, y),
            tuple(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)),
        )
    return gradient.resize((size, size), Image.NEAREST)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _draw_m_mark(draw: ImageDraw.ImageDraw, size: int) -> None:
    """用四条粗线画出几何化的字母 M。"""
    inset = size * 0.26
    left = inset
    right = size - inset
    top = inset * 1.02
    bottom = size - inset * 0.98
    stroke = round(size * STROKE_RATIO)
    half = stroke / 2

    joint_y = top + (bottom - top) * DIAGONAL_JOIN_RATIO
    center_x = (left + right) / 2

    draw.line([(left + half, top), (left + half, bottom)], fill=WHITE, width=stroke)
    draw.line([(right - half, top), (right - half, bottom)], fill=WHITE, width=stroke)
    draw.line(
        [(left + half, top + half), (center_x, joint_y)],
        fill=WHITE,
        width=stroke,
        joint="curve",
    )
    draw.line(
        [(right - half, top + half), (center_x, joint_y)],
        fill=WHITE,
        width=stroke,
        joint="curve",
    )


def _base_icon() -> Image.Image:
    radius = round(CANVAS * CORNER_RADIUS_RATIO)
    mask = _rounded_mask(CANVAS, radius)

    icon = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    icon.paste(_vertical_gradient(CANVAS, NAVY_PRIMARY, NAVY_DEEP).convert("RGBA"), (0, 0), mask)

    # 一条内描边让图标在深色任务栏上也有边界感。
    border = ImageDraw.Draw(icon)
    border.rounded_rectangle(
        (2, 2, CANVAS - 3, CANVAS - 3),
        radius=radius - 2,
        outline=(*ACCENT, 70),
        width=3,
    )

    _draw_m_mark(ImageDraw.Draw(icon), CANVAS)
    return icon


def _with_unread_dot(icon: Image.Image) -> Image.Image:
    """在右上角加一枚未读红点。托盘尺寸很小，所以红点要画得足够大。"""
    canvas = icon.copy()
    draw = ImageDraw.Draw(canvas)
    diameter = round(CANVAS * 0.36)
    margin = round(CANVAS * 0.03)
    box = (
        CANVAS - diameter - margin,
        margin,
        CANVAS - margin,
        CANVAS - margin,
    )
    # 先画一圈与底色同色的外环，让红点从方块里"浮"出来。
    ring = round(CANVAS * 0.035)
    draw.ellipse(
        (box[0] - ring, box[1] - ring, box[2] + ring, box[3] + ring),
        fill=NAVY_DEEP,
    )
    draw.ellipse(box, fill=UNREAD)
    return canvas


def _tray_icon(icon: Image.Image) -> Image.Image:
    """托盘图标按 Windows 通知区域的实际尺寸输出。"""
    return icon.resize((64, 64), Image.LANCZOS)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)

    base = _base_icon()
    base.save(ICON_DIR / "icon.png")

    for name, size in (("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256)):
        base.resize((size, size), Image.LANCZOS).save(ICON_DIR / name)

    base.save(
        ICON_DIR / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    _tray_icon(base).save(ICON_DIR / "tray.png")
    _tray_icon(_with_unread_dot(base)).save(ICON_DIR / "tray-unread.png")

    print(f"图标已生成到 {ICON_DIR}")


if __name__ == "__main__":
    main()
