#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提醒卡：齿轮位置 + 尺寸、卡片底色方案对比（开发用）。

背景：用户反馈「齿轮的大小和位置有点问题，但不知道放在哪里」。
与其猜，不如把候选方案并排渲染出来，用眼睛挑。

同时对比两种卡片底色：
- warm 暖做旧纸 #e9e5dc（当前 v1.2.3）
- cool 冷调柔灰 #dde2e7（更接近常驻泡泡的灰蓝）

跑：
    PYTHONPATH=<venv>/lib/python3.13/site-packages \
      <managed python> scripts/preview_gear.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402

import health_float as hf  # noqa: E402

TONE_BG = {"warm": "#e9e5dc", "cool": "#dde2e7"}

# 齿轮候选：(名称, 定位函数 or None=特殊处理)
# 卡片矩形 ALERT_CARD = (10, 10, 262, 198)
GEAR_PLACEMENTS = [
    ("A_right_top", "card_top_right", None),
    ("B_right_bottom", "card_bottom_right", None),   # 现状
    ("C_beside_title", "beside_title", None),
    ("D_left_bottom", "card_left_bottom", None),
]


def _card_pos(kind):
    """返回该方案下齿轮中心的绝对坐标。"""
    card = hf.ALERT_CARD
    if kind == "card_top_right":
        return (card[2] - 16, card[1] + 16)
    if kind == "card_bottom_right":
        return (card[2] - 16, card[3] - 16)
    if kind == "card_left_bottom":
        return (card[0] + 16, card[3] - 16)
    if kind == "beside_title":
        # 标题文字右边（标题是 13pt 粗体，4 个汉字）
        return (card[2] - 16, card[1] + 40)
    raise ValueError("未知方案: %r" % kind)


def grab(root, out_path, expect_w):
    """抓 layer=19 的浮窗并存成 PNG。"""
    try:
        import Quartz
        from AppKit import NSBitmapImageRep
        from io import BytesIO
        from PIL import Image
    except ImportError:
        print("[!] 缺少 pyobjc/Pillow")
        return False

    target = None
    for _ in range(60):
        for w in Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID):
            if w.get("kCGWindowOwnerPID") != os.getpid():
                continue
            if w.get("kCGWindowLayer") != 19:
                continue
            b = w.get("kCGWindowBounds", {})
            if not b.get("Width") or int(b["Width"]) != expect_w:
                continue
            target = w.get("kCGWindowNumber")
            break
        if target:
            break
        root.update()
        time.sleep(0.05)
    if not target:
        print("[X] 没找到浮窗")
        return False

    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        target,
        Quartz.kCGWindowImageBoundsIgnoreFraming)
    if img is None:
        print("[X] Quartz 拿不到窗口图像")
        return False

    rep = NSBitmapImageRep.alloc().initWithCGImage_(img)
    data = rep.representationUsingType_properties_(4, {})
    os.makedirs(os.path.join(HERE, "_preview"), exist_ok=True)
    Image.open(BytesIO(data)).convert("RGB").save(out_path)
    return True


def render_one(tone, kind, gear_r, out_path):
    """渲染一张：指定底色调 + 齿轮位置 + 齿轮半径。

    每次用**独立的 Tk root** —— 复用同一个 root 会残留上一个
    app 的画布元素，截图就串味了。

    齿轮位置通过改 hf.ALERT_GEAR_POS 常量来控制，
    而不是事后调 _move_gear ——
    FloatApp 里 _tick 每秒跑一次会调 _layout()，
    事后移动的齿轮会被拉回默认位置，之前 C/D 两个方案
    渲染出来跟 B 一模一样就是这么来的。
    """
    hf.ALERT_TONE = tone
    hf.ALERT_CARD_BG = TONE_BG[tone]
    hf.GEAR_R = gear_r
    hf.ALERT_GEAR_POS = _card_pos(kind)

    root = tk.Tk()
    root.withdraw()
    cfg = hf.load_config()
    app = hf.FloatApp(root, cfg)
    app.current = "sleep"
    app.auto_left = 93

    # 关键：先按提醒卡最终尺寸上屏，再切状态。
    # 反过来的话窗口服务器会保留旧尺寸那帧的合成缓存，
    # 截图里会出现「旧内容残影」。
    root.deiconify()
    try:
        root.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
    root.geometry("%dx%d+300+200" % (hf.ALERT[0], hf.ALERT[1]))
    root.update_idletasks()
    root.update()

    app._resize_to(*hf.ALERT)
    app._layout_alert()
    root.update()

    time.sleep(0.3)
    root.update()
    ok = grab(root, out_path, hf.ALERT[0])
    try:
        root.destroy()
    except Exception:
        pass
    return ok


def main():
    out_dir = os.path.join(HERE, "_preview")
    os.makedirs(out_dir, exist_ok=True)

    # 1) 齿轮位置（暖色底，当前半径）
    for key, kind, _ in GEAR_PLACEMENTS:
        path = os.path.join(out_dir, "gear_%s.png" % key)
        render_one("warm", kind, hf.GEAR_R, path)
        print("[OK]", path)

    # 2) 齿轮尺寸（位置固定右上角）
    for r in (3.6, 4.4, 5.2, 6.0):
        path = os.path.join(out_dir, "gearsize_r%.1f.png" % r)
        render_one("warm", "card_top_right", r, path)
        print("[OK]", path)

    # 3) 底色对比（齿轮固定右上角）
    for tone in ("warm", "cool"):
        path = os.path.join(out_dir, "tone_%s.png" % tone)
        render_one(tone, "card_top_right", hf.GEAR_R, path)
        print("[OK]", path)


if __name__ == "__main__":
    main()
