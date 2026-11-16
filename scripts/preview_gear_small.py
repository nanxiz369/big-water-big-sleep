#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""齿轮缩小后的实拍预览（开发用）。

两件事：
1. 把缩小后的提醒卡渲染出来，用眼睛确认「小得对不对」；
2. 在图上画出逻辑热区圈，直观确认它有没有跟标题/按钮打架。

热区是几何判定（_gear_hit），不是画出来的图元 ——
Tk 里 fill="" 的 oval 收不到点击，所以只能自己算距离。
预览里把圈画出来，是为了让「看不见的热区」变得可见。

跑：
    PYTHONPATH=<venv>/lib/python3.13/site-packages \
      <managed python> scripts/preview_gear_small.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402

import health_float as hf  # noqa: E402


def grab(root, out_path, expect_w):
    """抓 layer=19 的浮窗并存成 PNG。

    用 Quartz 按窗口号抓（kCGWindowImageBoundsIgnoreFraming），
    不用 screencapture -R：后者按屏幕物理像素裁剪，
    Retina 上 Tk 的逻辑坐标和它差一个缩放系数，
    而浮窗又是无边框置顶的，容易被别的窗口盖住截错。

    Quartz 需要 pyobjc，不一定装在跑脚本的默认 Python 里，
    所以脚本顶部会提示用带 pyobjc 的解释器运行。
    """
    try:
        import Quartz
        from AppKit import NSBitmapImageRep
        from io import BytesIO
        from PIL import Image
    except ImportError:
        print("[!] 缺少 pyobjc，请用装了 pyobjc 的解释器运行")
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
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Image.open(BytesIO(data)).convert("RGB").save(out_path)
    return True


def render(r, out_path, show_hit=True):
    """渲染一张指定齿轮半径的提醒卡，可选画出热区圈。"""
    hf.GEAR_R = r

    root = tk.Tk()
    root.withdraw()
    cfg = hf.load_config()
    app = hf.FloatApp(root, cfg)
    app.current = "sleep"
    app.auto_left = 93

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

    if show_hit:
        # 把「看不见的热区」画出来：红色虚线圈 = 逻辑点击范围
        gx, gy = app.gear_center
        hr = hf.GEAR_HIT_R
        app.cv.create_oval(gx - hr, gy - hr, gx + hr, gy + hr,
                           outline="#e05a4a", width=1, dash=(3, 2))
        # 底板半径也画一圈（浅色 = 悬停时亮起的范围）
        br = hf.GEAR_BG_R
        app.cv.create_oval(gx - br, gy - br, gx + br, gy + br,
                           outline="#3b7dd8", width=1)
        root.update()

    time.sleep(0.4)
    root.update()
    # 截图前必须把窗口提到最前：浮窗是置顶的，但别的置顶窗口
    # （比如 IDE 的悬浮窗）也可能盖在它上面，截出来就不是它了。
    try:
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
    except tk.TclError:
        pass
    root.update()
    time.sleep(0.4)
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

    # 1) 缩小后的三档半径（不带热区圈，看纯观感）
    for r in (4.2, 5.2):
        path = os.path.join(out_dir, "small_r%.1f.png" % r)
        render(r, path, show_hit=False)
        print("[OK]", path)

    # 2) 当前尺寸 + 热区圈（检查热区有没有跟标题/按钮打架）
    path = os.path.join(out_dir, "small_hit_r4.2.png")
    render(4.2, path, show_hit=True)
    print("[OK]", path)

    # 几何自检
    root = tk.Tk()
    root.withdraw()
    app = hf.FloatApp(root, hf.load_config())
    app.current = "sleep"
    app._resize_to(*hf.ALERT)
    app._layout_alert()
    root.update()
    cv = app.cv
    gx, gy = app.gear_center
    hr = hf.GEAR_HIT_R
    print("\n[几何自检] 提醒卡：齿轮中心", (gx, gy), "热区半径", hr)

    def circle_vs_rect(cx, cy, r, bb):
        """热区圆与矩形是否真的相交（算圆心到矩形的最短距离）。"""
        nx = min(max(cx, bb[0]), bb[2])
        ny = min(max(cy, bb[1]), bb[3])
        return (cx - nx) ** 2 + (cy - ny) ** 2 <= r * r

    def check(label):
        print(f"  --- {label} ---")
        for name, iid in (("标题", app.a_title_id),
                          ("标题emoji", app.a_icon_id),
                          ("副标题", app.a_sub_id),
                          ("按钮", app.a_btn_id),
                          ("提示", app.a_hint_id)):
            bb = cv.bbox(iid)
            if not bb:
                continue
            hit = circle_vs_rect(gx, gy, hr, bb)
            print(f"    {name}: bbox={bb} 落入热区={hit}")

    check("提醒卡")

    # 泡泡模式也要查一遍：齿轮位置不同，热区可能碰到倒计时/名字
    app.current = None
    app._resize_to(*hf.BUBBLE)
    app._layout_bubble()
    root.update()
    gx, gy = app.gear_center
    print("\n[几何自检] 泡泡：齿轮中心", (gx, gy), "热区半径", hr)
    for name, iid in (("时间", app.time_id), ("名字", app.name_id),
                      ("图标", app.icon_id)):
        bb = cv.bbox(iid)
        if not bb:
            continue
        hit = circle_vs_rect(gx, gy, hr, bb)
        print(f"    {name}: bbox={bb} 落入热区={hit}")
    root.destroy()


if __name__ == "__main__":
    main()
