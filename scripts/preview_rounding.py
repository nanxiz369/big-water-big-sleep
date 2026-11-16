#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""圆角矩形采样密度对比（开发用）。

背景：Tk 的 create_polygon(smooth=True) 会在直边上「鼓包」，
按钮顶边变成一串小台阶。改成 smooth=False + 真实圆弧采样后，
圆角变干净了，但采样点太少时圆角看着像倒角。

这个脚本把几种采样密度并排画出来，用眼睛挑。

跑： python3 scripts/preview_rounding.py
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_preview")


def arc_pts(steps, x1, y1, x2, y2, r):
    r = max(0.0, min(float(r), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    out = []
    for cx, cy, a0, a1 in [
            (x2 - r, y1 + r, -90.0, 0.0),
            (x2 - r, y2 - r, 0.0, 90.0),
            (x1 + r, y2 - r, 90.0, 180.0),
            (x1 + r, y1 + r, 180.0, 270.0)]:
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def main():
    import Quartz
    from AppKit import NSBitmapImageRep
    from io import BytesIO

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#e9e5dc")

    steps_list = [4, 6, 8, 12, 16, 20]
    cv = tk.Canvas(root, width=len(steps_list) * 130 + 20, height=110,
                   bg="#e9e5dc", highlightthickness=0)
    cv.pack()

    for i, steps in enumerate(steps_list):
        x0 = 20 + i * 130
        p = []
        for x, y in arc_pts(steps, x0, 25, x0 + 100, 60, 10):
            p.extend((x, y))
        cv.create_polygon(p, smooth=False, fill="#5b7086", outline="")
        cv.create_text(x0 + 50, 82, text="steps=%d" % steps,
                       font=("PingFang SC", 10), fill="#33465c")

    root.update()
    time.sleep(0.3)
    root.update()

    wl = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
    target = None
    for _ in range(60):
        for w in Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID):
            if w.get("kCGWindowOwnerPID") != os.getpid():
                continue
            if w.get("kCGWindowLayer") != 19:
                continue
            b = w.get("kCGWindowBounds", {})
            if not b.get("Width"):
                continue
            target = w.get("kCGWindowNumber")
            break
        if target:
            break
        root.update()
        time.sleep(0.05)
    if not target:
        print("[X] 没找到 layer=19 的浮窗")
        return

    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        target,
        Quartz.kCGWindowImageBoundsIgnoreFraming)
    if img is None:
        print("[X] Quartz 拿不到窗口图像")
        return

    rep = NSBitmapImageRep.alloc().initWithCGImage_(img)
    data = rep.representationUsingType_properties_(4, {})
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "rounding.png")
    Image.open(BytesIO(data)).convert("RGB").save(path)
    print("[OK]", path)
    root.destroy()


if __name__ == "__main__":
    main()
