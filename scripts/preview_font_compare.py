#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""泡泡字号「放大前 vs 放大后」并排对比图。

用途：用户说「字体大一点点」—— 「一点点」是个主观词，
光看代码里的 12→14 没法判断合不合适。
所以把两版真渲染出来拼一张图，一眼就能比。

用法：
    /tmp/pv/bin/python scripts/preview_font_compare.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import tkinter as tk  # noqa: E402

import health_float as hf  # noqa: E402
from preview_alert import grab_window  # noqa: E402

# (标签, 时间字号, 名称字号)
# 三版并排：上一版、我先做的 14/12、用户拍板的中间值 13/11。
VARIANTS = [
    ("上一版 12/10", 12, 10),
    ("我说有点大的 14/12", 14, 12),
    ("定稿 13/11", 13, 11),
]
SAMPLE_TIME = "19 分59秒"
SAMPLE_NAME = "看看远方"


def render(root, app, time_size, name_size, path):
    """按指定字号渲染一次泡泡并截图。"""
    app.cv.itemconfig(app.time_id, text=SAMPLE_TIME,
                       font=hf.ui_font(time_size, True))
    app.cv.itemconfig(app.name_id, text=SAMPLE_NAME,
                       font=hf.ui_font(name_size))
    app._resize_to(*hf.BUBBLE)
    app._layout_bubble()
    app.cv.update()
    root.update()
    root.update_idletasks()
    # 第一次抓容易抓到黑图 —— 窗口服务器还没把这一帧推到屏幕上。
    # 等一下再抓，第二次渲染就会正常。
    time.sleep(0.8)
    root.update()
    return grab_window(root, path, (hf.BUBBLE[0], hf.BUBBLE[1]))


def main():
    out_dir = os.path.join(HERE, "_preview")
    os.makedirs(out_dir, exist_ok=True)

    root = tk.Tk()
    root.deiconify()
    try:
        root.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
    root.geometry(f"{hf.BUBBLE[0]}x{hf.BUBBLE[1]}+300+200")
    root.update_idletasks()
    root.update()

    cfg = hf.load_config()
    app = hf.FloatApp(root, cfg)
    app.current = None

    shots = []
    for label, ts, ns in VARIANTS:
        path = os.path.join(out_dir, f"fontcmp_{ts}_{ns}.png")
        if render(root, app, ts, ns, path):
            shots.append((label, path))
        else:
            print("[!] 截图失败")
            root.destroy()
            return 1

    root.destroy()

    # 拼图
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[!] 缺 Pillow，只出单图")
        return 0

    imgs = [(label, Image.open(p).convert("RGB")) for label, p in shots]
    w = sum(i.width for _, i in imgs)
    h = max(i.height for _, i in imgs)
    gap = 28
    label_h = 26
    canvas = Image.new("RGB", (w + gap * (len(imgs) + 1),
                               h + label_h + gap * 2), (245, 246, 248))
    d = ImageDraw.Draw(canvas)
    x = gap
    for label, im in imgs:
        d.text((x, gap), label, fill=(60, 70, 85))
        canvas.paste(im, (x, gap + label_h))
        x += im.width + gap
    out = os.path.join(out_dir, "font_compare.png")
    canvas.save(out)
    print("[OK] %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
