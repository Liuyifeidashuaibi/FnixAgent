#!/usr/bin/env python3
"""
FnixAgent 图标生成器
从单一 SVG 源生成 Tauri 2 / iOS / Android / Windows 全部图标

需要:
- pip install pillow

用法:
    python generate.py
"""

from __future__ import annotations
import argparse
import sys
import io
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: 需要 pillow")
    print("  pip install pillow")
    sys.exit(1)


# 立方体几何参数(以 viewBox 512x512 为基础)
# 中心点 256,224(偏上,给外延节点和底部连线留空间)
# R = 120,顶部到 104,底部到 344,外延节点最远到 432,留 80 px 边距
CUBE_CX = 256
CUBE_CY = 224
CUBE_R = 120  # 立方体半宽

# 顶面 (top) 四点(菱形)
TOP_PTS = [
    (CUBE_CX, CUBE_CY - CUBE_R),         # 上顶点
    (CUBE_CX + CUBE_R, CUBE_CY),         # 右
    (CUBE_CX, CUBE_CY + CUBE_R),         # 下(中心)
    (CUBE_CX - CUBE_R, CUBE_CY),         # 左
]

# 左面 (left)
LEFT_PTS = [
    (CUBE_CX - CUBE_R, CUBE_CY),
    (CUBE_CX, CUBE_CY + CUBE_R),
    (CUBE_CX, CUBE_CY + 3*CUBE_R),
    (CUBE_CX - CUBE_R, CUBE_CY + 2*CUBE_R),
]

# 右面 (right)
RIGHT_PTS = [
    (CUBE_CX, CUBE_CY + CUBE_R),
    (CUBE_CX + CUBE_R, CUBE_CY),
    (CUBE_CX + CUBE_R, CUBE_CY + 2*CUBE_R),
    (CUBE_CX, CUBE_CY + 3*CUBE_R),
]

# 神经节点(放在合理距离,不超出画布)
# 立方体范围:x [136, 376], y [104, 344]
# 外延节点放在立方体外 50-60 px,确保不超出 512 范围
NODES_EXTERNAL = [
    (CUBE_CX + CUBE_R + 50, CUBE_CY - 30),          # 上右
    (CUBE_CX + CUBE_R + 50, CUBE_CY + 2*CUBE_R + 20), # 下右
    (CUBE_CX, CUBE_CY - CUBE_R - 50),                # 上
    (CUBE_CX - CUBE_R - 50, CUBE_CY - 30),          # 上左
    (CUBE_CX, CUBE_CY + 3*CUBE_R + 50),             # 下
]

NODES_VERTEX = [
    (CUBE_CX, CUBE_CY - CUBE_R),                   # 0: 上
    (CUBE_CX + CUBE_R, CUBE_CY),                   # 1: 上右
    (CUBE_CX, CUBE_CY + CUBE_R),                   # 2: 中
    (CUBE_CX - CUBE_R, CUBE_CY),                   # 3: 上左
    (CUBE_CX - CUBE_R, CUBE_CY + 2*CUBE_R),        # 4: 下左
    (CUBE_CX + CUBE_R, CUBE_CY + 2*CUBE_R),        # 5: 下右
    (CUBE_CX, CUBE_CY + 3*CUBE_R),                 # 6: 下
]

# 连线 (从 NODES_VERTEX 索引 到 NODES_EXTERNAL 索引)
CONNECTIONS = [
    (1, 0),  # 上右 -> 上右
    (5, 1),  # 下右 -> 下右
    (0, 2),  # 上 -> 上方
    (3, 3),  # 上左 -> 上左
    (6, 4),  # 下 -> 下方
]


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def render_isometric_cube(size: int, simplified: bool = False) -> Image.Image:
    """渲染等距立方体 + 神经节点(纯 Pillow)"""
    scale = size / 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, 'RGBA')

    def pt(p):
        return (int(p[0] * scale), int(p[1] * scale))

    # 顶面渐变填充(简化为多色拼接)
    top_pts = [pt(p) for p in TOP_PTS]
    left_pts = [pt(p) for p in LEFT_PTS]
    right_pts = [pt(p) for p in RIGHT_PTS]

    # 顶面:浅到深渐变
    for i in range(20):
        t = i / 19
        color = lerp_color((232, 232, 232), (160, 160, 160), t)
        # 简化为整面统一填充
    draw.polygon(top_pts, fill=(200, 200, 200, 255), outline=(10, 10, 10, 255))

    # 左面
    draw.polygon(left_pts, fill=(110, 110, 110, 255), outline=(10, 10, 10, 255))

    # 右面
    draw.polygon(right_pts, fill=(35, 35, 35, 255), outline=(10, 10, 10, 255))

    # 连线
    if not simplified or size >= 128:
            line_w = max(1, int(2 * scale))
            for v_idx, e_idx in CONNECTIONS:
                v = pt(NODES_VERTEX[v_idx])
                e = pt(NODES_EXTERNAL[e_idx])
                draw.line([v, e], fill=(255, 255, 255, 240), width=line_w)

    # 顶点节点 - 白色实心 + 黑色描边(在浅色背景下也可见)
    vertex_r = max(1, int(5 * scale))
    for p in NODES_VERTEX:
        x, y = pt(p)
        # 描边
        draw.ellipse([
            x - vertex_r - 1,
            y - vertex_r - 1,
            x + vertex_r + 1,
            y + vertex_r + 1,
        ], fill=(10, 10, 10, 255))
        # 实心
        draw.ellipse([
            x - vertex_r,
            y - vertex_r,
            x + vertex_r,
            y + vertex_r,
        ], fill=(255, 255, 255, 255))

    # 外延节点
    if not simplified or size >= 64:
        ext_r = max(1, int(8 * scale))
        for p in NODES_EXTERNAL:
            x, y = pt(p)
            # 光晕
            glow_r = ext_r * 2
            draw.ellipse([
                x - glow_r,
                y - glow_r,
                x + glow_r,
                y + glow_r,
            ], fill=(255, 255, 255, 80))
            # 描边
            draw.ellipse([
                x - ext_r - 2,
                y - ext_r - 2,
                x + ext_r + 2,
                y + ext_r + 2,
            ], fill=(10, 10, 10, 255))
            # 实心
            draw.ellipse([
                x - ext_r,
                y - ext_r,
                x + ext_r,
                y + ext_r,
            ], fill=(255, 255, 255, 255))

    return img


def save_png(img: Image.Image, path: Path, size: int = None) -> None:
    """保存 PNG(可选缩放)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if size and img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    img.save(path, format='PNG')
    print(f"  [OK] {path.name} ({img.size[0]}x{img.size[1]})")


# Tauri 2 标准输出
TAURI_ICONS = {
    "icon.png": 1024,
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "Square30x30Logo.png": 30,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89,
    "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142,
    "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284,
    "Square310x310Logo.png": 310,
    "StoreLogo.png": 50,
}


def generate_tauri(out: Path) -> None:
    print("\n[Tauri]")
    for name, size in TAURI_ICONS.items():
        # 小尺寸用 simplified(去除外部节点和光晕)
        simplified = size <= 64
        img = render_isometric_cube(max(size, 512), simplified=simplified)
        save_png(img, out / name, size)

    # macOS .icns 占位说明
    print("\n[macOS .icns]")
    print("  [!] .icns needs iconutil on macOS")
    print("  -> On macOS: cd apps/desktop-tauri/src-tauri/icons && iconutil -c icns icon.iconset")
    print("  -> Or use 'Icon Util' app to compose")

    # Windows .ico (多尺寸合成)
    print("\n[Windows .ico]")
    images = []
    for size in [16, 24, 32, 48, 64, 128, 256]:
        img = render_isometric_cube(max(size, 512), simplified=(size <= 32))
        images.append(img.resize((size, size), Image.LANCZOS))
    images[0].save(
        out / "icon.ico",
        format='ICO',
        sizes=[(i.size[0], i.size[1]) for i in images],
        append_images=images[1:],
    )
    print(f"  [OK] icon.ico (multi-size: 16-256)")


def generate_brand_assets(brand_out: Path) -> None:
    print("\n[Brand Assets]")
    brand_out.mkdir(parents=True, exist_ok=True)

    for name, size in [
        ("logo-16.png", 16),
        ("logo-32.png", 32),
        ("logo-64.png", 64),
        ("logo-128.png", 128),
        ("logo-256.png", 256),
        ("logo-512.png", 512),
        ("logo-1024.png", 1024),
    ]:
        simplified = size <= 64
        img = render_isometric_cube(max(size, 512), simplified=simplified)
        save_png(img, brand_out / name, size)

    # icon 系列(简化版,无外延节点)
    for name, size in [
        ("icon-16.png", 16),
        ("icon-32.png", 32),
        ("icon-64.png", 64),
        ("icon-128.png", 128),
        ("icon-256.png", 256),
        ("icon-512.png", 512),
        ("icon-1024.png", 1024),
    ]:
        img = render_isometric_cube(max(size, 512), simplified=True)
        save_png(img, brand_out / name, size)

    # favicon 系列(深色背景下白色图标)
    favicon = Image.new('RGBA', (32, 32), (10, 10, 14, 255))
    favicon_icon = render_isometric_cube(32, simplified=True)
    favicon.paste(favicon_icon, (0, 0), favicon_icon)
    save_png(favicon, brand_out / "favicon.png", 32)
    save_png(favicon, brand_out / "favicon.ico", 32)


def generate_og_image(brand_out: Path) -> None:
    """生成 1280x640 og-image(带真实文字)"""
    print("\n[OG Image 1280x640]")

    og = Image.new('RGB', (1280, 640), (10, 10, 14))
    draw = ImageDraw.Draw(og)

    # 字体(Windows 系统字体,跨平台失败则用 default)
    try:
        from PIL import ImageFont
        font_huge = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 80)
        font_large = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 36)
        font_medium = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 24)
        font_small = ImageFont.truetype("C:\\Windows\\Fonts\\consola.ttf", 20)
        font_zh = ImageFont.truetype("C:\\Windows\\Fonts\\msyhbd.ttf", 28)
    except Exception:
        from PIL import ImageFont
        font_huge = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_zh = ImageFont.load_default()

    # 左侧 Logo
    logo_size = 320
    logo = render_isometric_cube(logo_size, simplified=False)
    og.paste(logo, (80, 160), logo)

    # 右侧文字
    text_x = 500

    # 主标题:FnixAgent
    draw.text((text_x, 130), "FnixAgent", fill=(232, 232, 232), font=font_huge)

    # 副标题 (英文)
    draw.text((text_x, 230), "Local-First Desktop Agent Workbench",
              fill=(180, 180, 180), font=font_large)

    # 中文一行
    draw.text((text_x, 285), u"\u672c\u5730\u4f18\u5148 \u00b7 \u4e09\u5c42\u4efb\u52a1\u56fe \u00b7 BYOK",
              fill=(160, 160, 160), font=font_zh)

    # 分隔线
    draw.rectangle([text_x, 340, text_x + 600, 343], fill=(80, 80, 80))

    # 三个 tag chip
    chips = [("Rust + Python", (60, 60, 70), (200, 200, 200)),
             ("Tauri 2", (60, 60, 70), (200, 200, 200)),
             ("Markdown+Git", (60, 60, 70), (200, 200, 200))]
    chip_x = text_x
    for label, bg, fg in chips:
        bbox = draw.textbbox((0, 0), label, font=font_medium)
        w_chip = bbox[2] - bbox[0] + 24
        h_chip = 40
        draw.rectangle([chip_x, 380, chip_x + w_chip, 380 + h_chip], fill=bg)
        draw.rectangle([chip_x, 380, chip_x + w_chip, 380 + h_chip], outline=(120, 120, 120), width=1)
        draw.text((chip_x + 12, 388), label, fill=fg, font=font_medium)
        chip_x += w_chip + 12

    # 底部信息栏
    draw.rectangle([60, 580, 1220, 584], fill=(80, 80, 80))
    draw.text((80, 595), u"\u00a9 2024-2026 FnixAgent \u00b7 All Rights Reserved",
              fill=(140, 140, 140), font=font_small)
    draw.text((900, 595), "github.com/fnixagent/fnixagent",
              fill=(180, 180, 180), font=font_small)

    # 左下角装饰(几个小方块像状态指示)
    for i, c in enumerate([(80, 80, 80), (110, 110, 110), (140, 140, 140), (170, 170, 170)]):
        draw.rectangle([80 + i * 12, 540, 80 + i * 12 + 8, 548], fill=c)

    save_png(og, brand_out / "og-image.png")


def main() -> int:
    parser = argparse.ArgumentParser(description="FnixAgent 图标生成器")
    parser.add_argument(
        "--tauri-output",
        type=Path,
        default=Path("apps/desktop-tauri/src-tauri/icons"),
        help="Tauri 图标输出目录",
    )
    parser.add_argument(
        "--brand-output",
        type=Path,
        default=Path("assets/brand"),
        help="品牌资产输出目录",
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=["tauri", "brand"],
        choices=["tauri", "brand"],
    )
    args = parser.parse_args()

    print("== FnixAgent Icon Generator ==")
    print(f"[Targets] {args.platforms}")

    if "tauri" in args.platforms:
        args.tauri_output.mkdir(parents=True, exist_ok=True)
        generate_tauri(args.tauri_output)

    if "brand" in args.platforms:
        args.brand_output.mkdir(parents=True, exist_ok=True)
        generate_brand_assets(args.brand_output)
        generate_og_image(args.brand_output)

    print("\n[Done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())