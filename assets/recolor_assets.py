#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发用：把素材的灰底换成卡片色，生成提醒卡专用素材（assets/card_*.png）

为什么需要这一步
----------------
舷窗这张画是画在一片**渐变**灰底上的（顶部 #b8bdc4，底部偏暗），
所以它放在画布上时能完全融进去，看不出是一张图。

但提醒卡要的是「一个整体的框」：整张卡片一个颜色，图和字都在框里。
如果卡片换成别的颜色，这张画就会带着原来那片灰底，
在卡片上显出一个生硬的矩形 —— 又是「两个框」。

抠透明行不通：画的外圈有一大片柔和的光晕和投影，
按颜色抠会把它们一起抠掉、留下一圈毛边（实测过，很难看）。

所以用「按与背景的差值做平滑混合」的方式换色：
  越接近背景的像素（背景本身、渐变、投影）→ 越彻底地换成新底色
  离背景越远的像素（金属圈、云、叶片、光晕）→ 保持原样
中间用 smoothstep 过渡，所以看不到硬边。

关键点：背景是渐变的，不能拿单一颜色当基准。
所以先用四条边拟合一个双线性背景模型，逐像素跟「该位置的背景」
比较 —— 否则底部的暗区换不掉，会留下一条灰带。

跑一次即可，普通用户无需运行（仓库已带生成好的素材）。
需要： pip install pillow
"""

import math
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.png")

# 过渡宽度：像素与「该位置背景」的 L1 距离小于该值时开始被替换。
# 太大 → 金属圈被拽向背景、轮廓发虚；太小 → 渐变和投影残留成灰边。
# 40 是实测下来两头都还行的值。
T_MAX = 40

# 舷窗外圈的柔光晕 —— 径向淡出的半径（相对素材宽度）。
#
# 为什么需要它：舷窗自带一圈很宽的冷调光晕。在原来的灰底画布上，
# 这圈光晕和底色同色系，看不出来；但换成暖色卡片后，它就成了
# 一块**冷色矩形**被硬生生切在图框边缘上 —— 又是「两个框」，
# 只不过这次是「一个框 + 框里一块方块」。
#
# 光晕本身没法靠换色去掉（它离背景的距离超过了 T_MAX，
# 会被当成「物体」保留），但可以**让它淡出**：
# 给整张图加一层径向 alpha，中心（舷窗本体）不透明，
# 外圈（光晕）平滑归零，光晕就自然溶进卡片，看不到边界。
#
# R_IN  之内完全不透明（舷窗本体 + 紧贴的金属圈）
# R_OUT 之外完全透明（只剩卡片底色）
HALO_R_IN = 0.34     # 中心实心区半径
HALO_R_OUT = 0.60    # 完全淡出半径

# 色调方案：名称 → 卡片底色
TONES = {
    # 暖色做旧纸：和冷灰蓝的舷窗形成冷暖对比，复古水彩的调子
    "warm": (233, 229, 220),
    # 冷调柔灰：和原素材同色系，只是更浅更柔
    "cool": (221, 226, 231),
}

# 提醒卡左侧舷窗的尺寸（比常驻泡泡略小，给文字腾地方）
SIZES = [
    (106, 146),
]


def _avg(pixels):
    n = len(pixels)
    return tuple(sum(p[i] for p in pixels) / float(n) for i in range(3))


def fit_background(px, w, h):
    """用四条边拟合背景的双线性模型，返回四个角的颜色。

    背景是渐变的（上亮下暗、左右也有微差），
    用单一颜色当基准会把暗区漏掉。
    """
    def corner(pts):
        return _avg(pts)

    tl = corner([px[0, 0], px[1, 0], px[0, 1]])
    tr = corner([px[w - 1, 0], px[w - 1, 1], px[w - 2, 0]])
    bl = corner([px[0, h - 1], px[1, h - 1], px[0, h - 2]])
    br = corner([px[w - 1, h - 1], px[w - 2, h - 1], px[w - 1, h - 2]])
    return tl, tr, bl, br


def _bg_at(corners, x, y, w, h):
    tl, tr, bl, br = corners
    u = x / float(w - 1)
    v = y / float(h - 1)
    top = [tl[i] * (1 - u) + tr[i] * u for i in range(3)]
    bot = [bl[i] * (1 - u) + br[i] * u for i in range(3)]
    return [top[i] * (1 - v) + bot[i] * v for i in range(3)]


def recolor(im, bg_new):
    """把 im 的背景换成 bg_new，返回新的 RGB 图。"""
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    corners = fit_background(px, w, h)
    out = Image.new("RGB", (w, h))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            bgr, bgg, bgb = _bg_at(corners, x, y, w, h)
            d = abs(r - bgr) + abs(g - bgg) + abs(b - bgb)
            t = d / float(T_MAX)
            if t > 1.0:
                t = 1.0
            s = t * t * (3 - 2 * t)          # 0=纯背景 1=物体
            op[x, y] = (
                int(r + (bg_new[0] - bgr) * (1 - s)),
                int(g + (bg_new[1] - bgg) * (1 - s)),
                int(b + (bg_new[2] - bgb) * (1 - s)),
            )
    return out


def radial_alpha(im, r_in, r_out):
    """给图加一层径向 alpha：中心实心，外圈平滑淡出。

    舷窗自带一圈很宽的柔光晕。这圈光晕在灰底画布上和底色同色系，
    看不出来；换成暖色卡片后它就变成一块冷色方块被硬切在图框边上。
    换色治不了它（它离背景太远，会被当成物体保留），
    但让它淡出就能彻底消除边界。

    半径按图片宽度归一化，所以换尺寸也不用重调。
    """
    w, h = im.size
    cx, cy = w / 2.0, h / 2.0
    r_in_px = r_in * w
    r_out_px = r_out * w
    alpha = Image.new("L", (w, h), 0)
    ap = alpha.load()
    for y in range(h):
        dy = y - cy
        for x in range(w):
            d = math.hypot(x - cx, dy)
            if d <= r_in_px:
                v = 255
            elif d >= r_out_px:
                v = 0
            else:
                t = (d - r_in_px) / float(r_out_px - r_in_px)
                t = t * t * (3 - 2 * t)       # smoothstep
                v = int(255 * (1 - t))
            ap[x, y] = v
    return alpha


def main():
    base = Image.open(BASE)
    for tone, color in TONES.items():
        for (w, h) in SIZES:
            img = recolor(base, color).convert("RGBA")
            img.putalpha(radial_alpha(img, HALO_R_IN, HALO_R_OUT))
            img = img.resize((w, h), Image.LANCZOS)
            path = os.path.join(HERE, "card_%s_%dx%d.png" % (tone, w, h))
            img.save(path)
            print("card_%s_%dx%d.png  %s  (径向淡出 %.2f~%.2f)"
                  % (tone, w, h, color, HALO_R_IN, HALO_R_OUT))
    print("✅ 共 %d 个素材" % (len(TONES) * len(SIZES)))


if __name__ == "__main__":
    main()
