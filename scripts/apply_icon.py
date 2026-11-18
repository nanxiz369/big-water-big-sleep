#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一张方形图标原图转成 macOS/Linux 都能用的 assets/app-icon.png。

为什么要写这个脚本，而不是直接 cp 一张 PNG 过去：

新图标「Health Float icon B · 眺远方.png」是 2048x2048 的 **RGB**，
四角是接近纯白的实心像素（253~255），**没有 alpha 通道**。
macOS 的图标必须自带圆角之外的透明区域，否则 Finder / Dock 会把它
显示成一个「白色方块贴了个小图」。

旧图标 assets/app-icon.png 是 1024x1024 的 RGBA，四角 alpha=0，
说明项目一直用的就是「自带透明圆角」的路子。

处理步骤：
  1. 用「饱和度」定位内容边界 —— 白色背景 sat≈0，彩色内容 sat≫0；
  2. 裁到内容，去掉四周白边；
  3. 加 macOS 风格的圆角遮罩（squircle），边缘羽化；
  4. 把最外圈残留的「半白」过渡像素设为透明。

**第 4 步只作用于外圈**：图标内部有一朵白云，白色的 sat 也很低，
全局按饱和度抠会连云一起抠没了。

全程用 PIL 的 C 级算子（point / lighter / darker / getbbox / GaussianBlur），
避免 400 万像素的 Python 循环。

用法：
    python3 scripts/apply_icon.py "/path/to/新图标.png"

原图不会被修改（个人目录里的文件一律只读）。
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(REPO_ROOT, "assets", "app-icon.png")
SIZE = 1024

# 「这是白底而不是图标内容」的饱和度阈值（通道极差 max-min）。
# 纯白背景 sat = 1~2；边缘抗锯齿的半白像素 sat ≈ 20；
# 天空蓝 sat = 39；山丘绿 sat = 96。
SAT_BG = 10

# macOS Big Sur 之后图标是 squircle，圆角半径约为边长的 22.4%。
SQUIRCLE_RATIO = 0.235


def saturation_mask(img):
    """返回通道极差（max-min）的 L 模式图，用作饱和度蒙版。"""
    r, g, b = img.convert("RGB").split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    return ImageChops.difference(mx, mn)


def build_alpha_mask(size, feather=2):
    """生成 macOS 风格的圆角遮罩（L 模式，255=不透明）。"""
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    radius = int(min(size) * SQUIRCLE_RATIO)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                        radius=radius, fill=255)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return mask


def trim_transparent_border(rgba, ring=2):
    """把最外圈 ring 像素里的「近白/低饱和」过渡像素设为透明。

    只动外圈 —— 内部的白色云朵必须原样保留。
    """
    w, h = rgba.size
    sat = saturation_mask(rgba).point(lambda v: 255 if v > SAT_BG else 0)
    px = rgba.load()
    sp = sat.load()
    for y in range(h):
        for x in range(w):
            if x < ring or y < ring or x >= w - ring or y >= h - ring:
                if sp[x, y] == 0:
                    r, g, b, _ = px[x, y]
                    px[x, y] = (r, g, b, 0)
    return rgba


def apply_icon(src_path):
    src = Image.open(src_path)
    print(f"原图: {src.size} {src.mode}  <- {src_path}")

    # 1. 在原图上直接精确定位内容边界。
    #    （之前用 256px 缩略图探测，缩放误差让 bbox 多吃了 ~10px 白边，
    #      结果图标四周出现一圈明显的白色环。）
    mask = saturation_mask(src).point(lambda v: 255 if v > SAT_BG else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit("整张图都是白色，没有找到图标内容。")
    print(f"内容包围盒: {bbox}  (宽 {bbox[2]-bbox[0]} × 高 {bbox[3]-bbox[1]})")

    # 2. 裁到内容
    cropped = src.crop(bbox).convert("RGB")

    # 3. 缩到 1024 内，保持比例
    factor = SIZE / max(cropped.size)
    new_size = (max(1, round(cropped.size[0] * factor)),
                max(1, round(cropped.size[1] * factor)))
    cropped = cropped.resize(new_size, Image.LANCZOS)

    # 4. 加透明圆角 + 清掉外圈残留白边
    out = cropped.convert("RGBA")
    out.putalpha(build_alpha_mask(new_size))
    out = trim_transparent_border(out, ring=2)

    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    out.save(TARGET, "PNG")
    print(f"\n✓ 已写入 {TARGET}")
    print(f"  {out.size} {out.mode}")

    # 5. 复核
    px = out.load()
    w, h = out.size
    corners = [px[0, 0][3], px[w - 1, 0][3], px[0, h - 1][3], px[w - 1, h - 1][3]]
    edge = [px[1, h // 2][3], px[w - 2, h // 2][3],
            px[w // 2, 1][3], px[w // 2, h - 2][3]]
    cloud = px[w // 2, int(h * 0.28)][3]      # 云朵附近，必须不透明
    print(f"  四角 alpha: {corners}  {'✓ 全透明' if max(corners) < 40 else '✗'}")
    print(f"  边中点 alpha: {edge}  (应为 255)")
    print(f"  中心 alpha: {px[w // 2, h // 2][3]}  (应为 255)")
    print(f"  云区 alpha: {cloud}  (白色云必须保留 255)")
    if max(corners) >= 40 or min(edge) < 200:
        raise SystemExit("图标处理不合格，中止。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    apply_icon(sys.argv[1])
