"""make_icon.py — 生成机器人启动器的 .ico 图标

画一个圆角方块 + 猫耳 + 眼睛的简笔图标（幻梦默认人格是猫娘），
配色取项目主题色 #8B7BFF（README 徽章色）。
不依赖字体，纯图形绘制，避免中文字体缺失问题。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(r"D:\QQBot\bot.ico")
SIZE = 256


def rounded_bg(size: int) -> Image.Image:
    """圆角矩形渐变背景（紫 → 蓝）"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    px = grad.load()
    # 主题渐变：#8B7BFF(139,123,255) → #4D6BFE(77,107,254)
    c1 = (139, 123, 255)
    c2 = (77, 107, 254)
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            px[x, y] = (
                int(c1[0] + (c2[0] - c1[0]) * t),
                int(c1[1] + (c2[1] - c1[1]) * t),
                int(c1[2] + (c2[2] - c1[2]) * t),
                255,
            )
    # 圆角遮罩
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255
    )
    img.paste(grad, (0, 0), mask)
    return img


def draw_face(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    s = img.size[0]
    white = (255, 255, 255, 255)
    dark = (58, 48, 120, 255)

    # 猫耳（两个三角形，先画白色外轮廓再画内部深色）
    ear_w = int(s * 0.20)
    ear_h = int(s * 0.24)
    for base_x in (int(s * 0.22), int(s * 0.58)):
        outer = [
            (base_x, int(s * 0.34)),
            (base_x + ear_w, int(s * 0.34)),
            (base_x + ear_w // 2, int(s * 0.34) - ear_h),
        ]
        d.polygon(outer, fill=white)
        inner = [
            (base_x + int(ear_w * 0.26), int(s * 0.33)),
            (base_x + int(ear_w * 0.74), int(s * 0.33)),
            (base_x + ear_w // 2, int(s * 0.33) - int(ear_h * 0.5)),
        ]
        d.polygon(inner, fill=(255, 190, 215, 255))

    # 脸：白色圆角方块
    face = [int(s * 0.16), int(s * 0.32), int(s * 0.84), int(s * 0.87)]
    d.rounded_rectangle(face, radius=int(s * 0.16), fill=white)

    # 眼睛（两只深色圆）
    eye_r = int(s * 0.062)
    for cx in (int(s * 0.36), int(s * 0.64)):
        cy = int(s * 0.55)
        d.ellipse([cx - eye_r, cy - eye_r, cx + eye_r, cy + eye_r], fill=dark)
        # 高光
        hr = int(eye_r * 0.36)
        d.ellipse(
            [cx - eye_r // 3 - hr, cy - eye_r // 3 - hr,
             cx - eye_r // 3 + hr, cy - eye_r // 3 + hr],
            fill=(255, 255, 255, 255),
        )

    # 嘴：小弧线（两段组成 w 形）
    my = int(s * 0.71)
    d.arc([int(s * 0.44), my - int(s * 0.04), int(s * 0.51), my + int(s * 0.05)],
          0, 180, fill=dark, width=max(2, int(s * 0.018)))
    d.arc([int(s * 0.49), my - int(s * 0.04), int(s * 0.56), my + int(s * 0.05)],
          0, 180, fill=dark, width=max(2, int(s * 0.018)))


def main() -> None:
    base = rounded_bg(SIZE)
    draw_face(base)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    base.save(OUT, format="ICO", sizes=sizes)
    print(f"图标已生成: {OUT}  ({OUT.stat().st_size} 字节, 含 {len(sizes)} 种尺寸)")


if __name__ == "__main__":
    main()
