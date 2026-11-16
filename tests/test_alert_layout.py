#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提醒卡排版守卫测试

这一组的每个用例都对应一个**真实发生过的**排版 bug，
不是「为了覆盖率而写」的测试。

背景：2026-11-13 用户两次发截图投诉提醒卡「丑成什么样了」。
排查下来是 6 个真问题，其中 4 个不报错、不崩溃，肉眼才看得见：

  1. 面板只有 110pt 宽，15pt 粗体标题（emoji + 4 汉字）撑到边缘
  2. 标题与副标题几乎贴在一起，没有呼吸感
  3. 副标题靠 width= 自动折行，把「明天还有满格的自己」断成
     「明天还有满格 / 的自己」，语义被拦腰截断
  4. 按钮底板用 cv.move 定位（move 是相对位移且不改尺寸），
     缩成一个 10x10 的小方块；按钮文字坐标从未设置，永远停在 (0,0)
  5. 齿轮 ⚙ 和底部提示文字挤在同一行，直接叠在一起
  6. 字符「⚙」(U+2699) 在 macOS Tk 里没有可用字形，静默渲染成空白 ——
     设置入口完全看不见

所以这里的核心断言不是「长什么样」，而是「不能再退回那些坏状态」。

运行： python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest

# 让控制台输出不依赖系统编码：Windows 是 cp1252，
# 打印中文断言消息时会抛 UnicodeEncodeError，
# 把「测试失败」变成「测试崩溃」，真正的失败原因反而看不见。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _utf8_console  # noqa: F401,E402


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402
import tkinter.font  # noqa: E402

import health_float as hf  # noqa: E402

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    """读仓库里的文本文件（相对仓库根）。"""
    with open(os.path.join(ROOT_DIR, rel_path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestAlertLayout(unittest.TestCase):
    """提醒卡排版：宽度、层级、按钮、齿轮"""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        # 窗口要「显示但全透明」，不能用 withdraw()。
        #
        # 为什么：Tk 的 event_generate 只会把事件投递给**已映射**
        # 的 widget，withdraw() 掉的窗口收不到任何事件 ——
        # 实测 withdraw() 之后连 <Motion> 都投不进来。
        # 而这一组里有几条测试必须发真事件（点齿轮开设置），
        # 用直接调函数的方式测就绕过了整套绑定，测不出「点不中」。
        #
        # alpha=0 让窗口完全看不见（测试时不会在屏幕上闪一个浮窗），
        # 但它仍然是 mapped 的，事件照收不误。
        cls.root.deiconify()
        try:
            cls.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.cfg = hf.load_config()
        cls.app = hf.FloatApp(cls.root, cls.cfg)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        # 上一条用例可能把 _open_settings 换成打桩版本，
        # 必须还原，否则后面的用例会跟着一起「假通过」。
        if not hasattr(self.app, "_open_settings_real"):
            self.app._open_settings_real = self.app._open_settings
        else:
            self.app._open_settings = self.app._open_settings_real
        self.app.current = "sleep"
        self.app.auto_left = 93
        self.app._resize_to(*hf.ALERT)
        self.app._layout_alert()
        self.app._update_auto_hint()
        self.root.update()

    # ---------- 文字栏宽度 ----------
    def test_panel_wide_enough_for_longest_title(self):
        """最宽的标题组必须放得进文字栏，不能顶到右边缘。

        标题组 = emoji + 间隔 + 汉字标题。
        用真实字体度量算，而不是写死数字 —— 换字体/字号时测试仍有意义。
        """
        content_w = hf.ALERT_TEXT[1] - hf.ALERT_TEXT[0] - 16   # 左右各留 8pt

        f_title = tkinter.font.Font(root=self.root, font=hf.ui_font(13))
        f_icon = tkinter.font.Font(root=self.root, font=hf.ui_font(14))
        for key, (title, _sub, icon, _, _) in hf.ALERT_META.items():
            group = (f_icon.measure(icon) + 6 + f_title.measure(title))
            self.assertLessEqual(
                group, content_w,
                f"「{title}」标题组宽 {group} > 文字栏内容宽 {content_w}，会溢出")

    def test_title_fits_inside_panel(self):
        """标题的实际绘制范围必须在文字栏内（不是估算，是 bbox）"""
        cv = self.app.cv
        for key in hf.ALERT_META:
            self.app.current = key
            self.app._layout_alert()
            self.root.update()
            for iid in (self.app.a_icon_id, self.app.a_title_id):
                bb = cv.bbox(iid)
                self.assertIsNotNone(bb, f"{key}: 标题元素没画出来")
                self.assertGreaterEqual(bb[0], hf.ALERT_TEXT[0],
                                        f"{key}: 标题左侧超出文字栏")
                self.assertLessEqual(bb[2], hf.ALERT_TEXT[1],
                                     f"{key}: 标题右侧超出文字栏: {bb}")

    def test_subtitle_lines_do_not_overflow_panel(self):
        """副标题每一行都必须放得进文字栏。

        这是「明天还有满格的自己」被断成两截的那个 bug 的守卫。
        """
        cv = self.app.cv
        f_sub = tkinter.font.Font(root=self.root, font=hf.ui_font(10))
        for key, (_t, sub, _i, _, _) in hf.ALERT_META.items():
            for line in sub.split("\n"):
                w = f_sub.measure(line)
                self.assertLessEqual(
                    w, hf.ALERT_TEXT[1] - hf.ALERT_TEXT[0] - 16,
                    f"「{key}」副标题行「{line}」宽 {w}，超出文字栏")

    def test_subtitle_uses_manual_line_breaks_only(self):
        """副标题不能靠 width= 自动折行。

        自动折行会在语义中间断开（「明天还有满格 / 的自己」）。
        现在文案自带 \\n，交给 Tk 的 width 反而会二次折行。
        width=0 表示「不自动折行」，这是我们要的状态。
        """
        cv = self.app.cv
        width = cv.itemcget(self.app.a_sub_id, "width")
        self.assertEqual(
            int(width or 0), 0,
            "副标题不该设 width= 让 Tk 自动折行 —— "
            "那会把句子拦腰截断。行数由文案里的 \\n 决定。")

    # ---------- 垂直节奏 ----------
    def test_vertical_rhythm_has_breathing_room(self):
        """标题、副标题、按钮、提示之间都要有呼吸，不能贴在一起。

        用户截图里最刺眼的就是「该睡觉啦」和「放下屏幕」几乎重叠。
        """
        cv = self.app.cv
        title = cv.bbox(self.app.a_title_id)
        sub = cv.bbox(self.app.a_sub_id)
        self.assertGreaterEqual(
            sub[1] - title[3], 8,
            f"副标题贴着标题了（间距 {sub[1] - title[3]}）")

        btn = cv.bbox(self.app.a_btn_id)
        self.assertGreaterEqual(
            btn[1] - sub[3], 8,
            f"按钮贴着副标题了（间距 {btn[1] - sub[3]}）")

        hint = cv.bbox(self.app.a_hint_id)
        self.assertGreaterEqual(
            hint[1] - btn[3], 8,
            f"提示文字贴着按钮了（间距 {hint[1] - btn[3]}）")

    def test_elements_stay_inside_panel_vertically(self):
        """所有文字元素都要在卡片的上下边界内"""
        cv = self.app.cv
        for iid in (self.app.a_icon_id, self.app.a_title_id,
                    self.app.a_sub_id, self.app.a_hint_id):
            bb = cv.bbox(iid)
            self.assertIsNotNone(bb)
            self.assertGreaterEqual(bb[1], hf.ALERT_CARD[1],
                                    f"{iid} 超出卡片上边")
            self.assertLessEqual(bb[3], hf.ALERT_CARD[3],
                                 f"{iid} 超出卡片下边: {bb}")

    # ---------- 按钮 ----------
    def test_button_has_visible_label(self):
        """按钮必须有文字，且文字居中在按钮上。

        之前 a_btn_txt 的坐标从未设置过，文字永远停在 (0,0)，
        截图里那个按钮只剩一个空的小方块。
        """
        cv = self.app.cv
        self.assertEqual(cv.itemcget(self.app.a_btn_txt, "state"), "normal",
                         "按钮文字不可见")
        self.assertTrue(cv.itemcget(self.app.a_btn_txt, "text").strip(),
                        "按钮文字是空的")
        tb = cv.bbox(self.app.a_btn_txt)
        bb = cv.bbox(self.app.a_btn_id)
        self.assertIsNotNone(tb, "按钮文字没画出来")
        self.assertIsNotNone(bb, "按钮底板没画出来")
        # 文字必须落在按钮底板范围内
        self.assertGreaterEqual(tb[0], bb[0] - 2, "按钮文字跑到底板左边了")
        self.assertLessEqual(tb[2], bb[2] + 2, "按钮文字跑到底板右边了")
        self.assertGreaterEqual(tb[1], bb[1] - 2, "按钮文字跑到底板上边了")
        self.assertLessEqual(tb[3], bb[3] + 2, "按钮文字跑到底板下边了")

    def test_button_text_has_no_checkmark(self):
        """按钮文案里不能有勾。

        U+2713 不在 PingFang SC 里，macOS 会回退到别的字体渲染它 ——
        实测回退出来的是**衬线斜体**的勾，和旁边黑体的「知道了」
        完全是两套字体，看着像贴上去的一个外来物。
        用户截图里就是这么个东西，他还以为是什么东西挡住了按钮。

        同理，「保存 ✓」在设置面板里也是一样的毛病。
        """
        cv = self.app.cv
        text = cv.itemcget(self.app.a_btn_txt, "text")
        for mark in ("✓", "✔", "√"):
            self.assertNotIn(
                mark, text,
                f"按钮文案又带上了 {mark} —— 它在 PingFang 里没有字形，"
                "会回退成衬线斜体，跟旁边的中文不是一套字体")

        # 设置面板的两个按钮同样不能带
        import re
        src = _read("health_float.py")
        for m in re.finditer(r'text="([^"]*)"', src):
            label = m.group(1)
            for mark in ("✓", "✔", "√"):
                self.assertNotIn(
                    mark, label,
                    f"界面文案 {label!r} 里带了 {mark} —— 同样的字体回退问题")

    def test_button_size_is_stable_across_layouts(self):
        """反复 layout 后按钮尺寸不能变。

        用 cv.move 定位多边形是相对位移：位置会漂，尺寸也不会变。
        必须用 cv.coords 给完整点集。
        """
        cv = self.app.cv
        before = cv.bbox(self.app.a_btn_id)
        for _ in range(5):
            self.app._layout_alert()
        after = cv.bbox(self.app.a_btn_id)
        self.assertEqual(before, after,
                         f"按钮几何在多次 layout 后变了: {before} -> {after}")
        w = before[2] - before[0]
        self.assertGreater(w, 40, f"按钮太窄了（{w}pt），像个残缺的小方块")

    def test_button_text_positioned_within_button(self):
        """按钮文字必须跟着按钮走（不能停在画布原点）"""
        cv = self.app.cv
        tb = cv.bbox(self.app.a_btn_txt)
        self.assertIsNotNone(tb)
        self.assertGreater(tb[0], 0, "按钮文字还停在画布原点")

    # ---------- 齿轮 ----------
    def test_gear_is_not_a_missing_glyph_character(self):
        """齿轮必须是 Canvas 图元，不能是字符「⚙」。

        U+2699 在 macOS Tk 里没有可用字形，会静默渲染成空白 ——
        设置入口完全看不见，而且不报任何错。
        """
        cv = self.app.cv
        self.assertNotEqual(
            cv.type(self.app.gear_id), "text",
            "齿轮又变回字符了 —— macOS 上那个字符没有字形，等于隐形")
        # 齿轮整组图元都要有真实尺寸
        for iid in (self.app.gear_id,) + tuple(self.app.gear_extra):
            bb = cv.bbox(iid)
            self.assertIsNotNone(bb, "齿轮图元没画出来")
            self.assertGreater(bb[2] - bb[0], 0)

    def test_gear_is_visible_and_big_enough(self):
        """齿轮必须可见，且有一定体量（太小等于看不见）。

        下限 8pt：实测 r=4.2（外圈 8pt）渲染出来只剩一个小点，
        完全看不出是齿轮，「设置入口」等于消失了。
        现在的 4.7 是这条线上的安全值。
        """
        cv = self.app.cv
        self.assertEqual(cv.itemcget(self.app.gear_id, "state"), "normal",
                         "齿轮不可见")
        bb = cv.bbox(self.app.gear_id)
        self.assertGreaterEqual(bb[2] - bb[0], 8,
                                "齿轮太小了（<8pt），实际看不见")
        # 含齿整体也不能小于 14pt —— 齿块是「这是个齿轮」的主要识别特征
        xs, ys = [], []
        for iid in (self.app.gear_id,) + tuple(self.app.gear_extra):
            b = cv.bbox(iid)
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
        self.assertGreaterEqual(max(xs) - min(xs), 14,
                                "齿轮含齿整体太小了，已经认不出是齿轮")

    def test_gear_stays_small(self):
        """齿轮不能变大。

        用户连着说了两次「齿轮还要再小一些」「整体都缩小一些」。
        5.2 那版（外圈 10pt / 含齿 20pt）渲染出来是一个实心深色块，
        比「知道了」按钮还重，像主按钮。

        这条守的是「别改回去」：齿轮是整个界面里最容易被
        「顺手调大一点」的元素，而变大之后用户一定会再投诉一次。
        """
        self.assertLessEqual(hf.GEAR_R, 5.0,
                             "齿轮又变大了（半径 > 5.0）—— "
                             "用户明确要求整体缩小")
        bb = self.app.cv.bbox(self.app.gear_id)
        self.assertLessEqual(bb[2] - bb[0], 11,
                              "齿轮外圈又变大了（>11pt），会抢主体内容的戏")

    def test_gear_hit_zone_is_bigger_than_the_gear(self):
        """逻辑热区必须明显大于可见齿轮。

        齿轮缩到 9.4pt 之后，鼠标根本瞄不准那 9 个像素。
        点击判定靠 GEAR_HIT_R 的距离热区，所以热区必须比可见齿轮大，
        否则「看得见」和「点得中」会脱节。

        这条不能靠 Tk 的命中检测兜底：Tk 里 fill="" 的图元收不到点击，
        透明热区画不出来，只能自己算距离。
        """
        self.assertGreater(hf.GEAR_HIT_R, hf.GEAR_R,
                           "热区必须比可见齿轮大，否则小齿轮点不中")
        # 至少要有一个 22pt 左右的判定圈，鼠标才好瞄
        self.assertGreaterEqual(hf.GEAR_HIT_R * 2, 20,
                                "热区直径太小了（<20pt），小图标很难点中")

    def test_gear_hit_zone_does_not_swallow_title(self):
        """热区不能碰到标题文字。

        热区是看不见的圆形判定圈，半径 11pt 比可见齿轮大一圈半。
        齿轮位置如果往左/往下挪一点，热区就会盖住标题的最后一个字 ——
        用户点标题右边缘会误开设置面板，而且完全不知道发生了什么。

        判据用「圆心到矩形的最短距离」，不是 bbox 粗相交：
        热区圆和标题 bbox 的**矩形**相交是正常的（右上角擦边），
        只有真的压到字上才算问题。
        """
        cv = self.app.cv
        gx, gy = self.app.gear_center
        hr = hf.GEAR_HIT_R
        for label, iid in (("标题", self.app.a_title_id),
                           ("标题emoji", self.app.a_icon_id),
                           ("副标题", self.app.a_sub_id),
                           ("按钮", self.app.a_btn_id),
                           ("底部提示", self.app.a_hint_id)):
            bb = cv.bbox(iid)
            self.assertIsNotNone(bb, f"{label} 没有布局")
            nx = min(max(gx, bb[0]), bb[2])
            ny = min(max(gy, bb[1]), bb[3])
            dist2 = (gx - nx) ** 2 + (gy - ny) ** 2
            self.assertGreater(
                dist2, hr * hr,
                f"{label} 落进了齿轮热区里 —— 点它会误开设置面板: "
                f"gear=({gx},{gy}) r={hr} {label}={bb}")

    def test_gear_click_uses_distance_not_tk_hit(self):
        """齿轮的点击判定必须走距离，不能依赖 Tk 的 tag 命中。

        Tk 画布只有「有填充的图元」才收得到点击，
        fill="" 的透明 oval 是死的 —— 点了它 tag 绑定完全不响。
        所以齿轮一旦缩小，就必须靠 Python 侧的距离判定。

        这条测试守的是「别把齿轮改回 tag 绑定」：
        那样齿轮会变得又大又难点中，而且没人知道为什么。
        """
        src = _read("health_float.py")
        self.assertIn("def _gear_hit(", src,
                      "齿轮的距离判定函数不见了")
        self.assertIn("self._gear_hit(e.x, e.y)", src,
                      "齿轮点击没有走距离判定")
        # 齿轮本体上不能再挂 <Button-1> 的 tag 绑定
        self.assertNotIn(
            'tag_bind("gear", "<Button-1>"', src,
            "齿轮又挂回 tag 点击绑定了 —— Tk 里那只有效于可见像素，"
            "小齿轮会变得极难点中")

    def test_gear_does_not_overlap_hint_text(self):
        """齿轮不能和底部提示文字叠在一起。

        用户截图里齿轮和「93 秒后自动消失」是重叠的。
        """
        cv = self.app.cv
        gear = cv.bbox(self.app.gear_id)
        hint = cv.bbox(self.app.a_hint_id)
        self.assertIsNotNone(gear)
        self.assertIsNotNone(hint)
        overlap = not (gear[2] < hint[0] or gear[0] > hint[2]
                       or gear[3] < hint[1] or gear[1] > hint[3])
        self.assertFalse(overlap,
                         f"齿轮和提示文字重叠了: gear={gear} hint={hint}")

    def test_gear_not_covered_by_title(self):
        """齿轮必须在标题文字之上（z-order）。

        标题「该睡觉啦」的 bbox 一直伸到 x≈283，和右上角的齿轮
        重叠 —— 齿轮层级不够就会被标题压在下面看不见。
        """
        cv = self.app.cv
        above = cv.find_above(self.app.gear_id)
        while above:
            state = cv.itemcget(above, "state")
            if state == "normal" and cv.type(above) == "text":
                txt = cv.itemcget(above, "text")
                if txt in ("该睡觉啦", "看看远方", "起来动动",
                           "喝杯水吧", "去洗澡啦"):
                    self.fail(f"齿轮被标题「{txt}」压在下面了")
            above = cv.find_above(above)

    def test_gear_moves_as_a_group(self):
        """整组齿轮图元必须一起移动，不能散架。

        判据不是「所有图元同心」—— 齿块本来就偏心（它们在半径 8.6
        的圆周上，外圈半径只有 6.8）。真正的判据是**相对位置不变**：
        每个图元的 bbox 相对齿轮中心的偏移量在移动前后必须一致。
        """
        cv = self.app.cv
        ids = (self.app.gear_id,) + tuple(self.app.gear_extra)

        def offsets(cx, cy):
            out = []
            for iid in ids:
                bb = cv.bbox(iid)
                out.append((bb[0] - cx, bb[1] - cy, bb[2] - cx, bb[3] - cy))
            return out

        before_c = self.app.gear_center
        before = offsets(*before_c)
        self.app._move_gear(200, 120)
        after = offsets(200, 120)

        for i, (b, a) in enumerate(zip(before, after)):
            for bv, av in zip(b, a):
                self.assertAlmostEqual(
                    bv, av, delta=0.6,
                    msg=f"齿轮图元 {i} 移动后相对位置变了（散架）: "
                        f"{b} -> {a}")

    # ---------- 齿轮点击（真事件）----------
    def test_clicking_gear_opens_settings(self):
        """真点一下齿轮，必须打开设置面板。

        这是齿轮缩小后的头号风险：视觉只有 9.4pt，
        如果点击判定没跟着改，点它就什么都不会发生 ——
        「设置入口」名存实亡。

        用 event_generate 发真实事件，走完整的绑定链路，
        而不是直接调 _open_settings —— 后者绕过了一切，
        测不出「点不中」这种问题。

        _open_settings 被换成打桩版本：真的开面板会留下一个
        没人关的窗口（测试结束时它还在，容易影响后续用例）。
        """
        opened = []
        self.app._open_settings = lambda: opened.append(True)
        gx, gy = self.app.gear_center
        self.app.cv.event_generate("<Button-1>", x=int(gx), y=int(gy))
        self.app.root.update()
        self.assertTrue(opened, "点齿轮没有打开设置面板")

    def test_clicking_beside_gear_also_opens_settings(self):
        """点齿轮旁边的空白（热区内）也要能打开设置。

        齿轮只有 9.4pt 直径，鼠标瞄准它很费劲。
        热区的意义就在这里：鼠标停在齿轮附近的空白处也算命中。
        这个点在 Tk 里是点不到任何图元的 ——
        只有距离判定能接住。
        """
        opened = []
        self.app._open_settings = lambda: opened.append(True)
        gx, gy = self.app.gear_center
        # 热区边缘内侧，且明确不在齿轮可见像素上
        d = hf.GEAR_HIT_R - 2
        self.app.cv.event_generate("<Button-1>", x=int(gx + d), y=int(gy))
        self.app.root.update()
        self.assertTrue(opened,
                        "点齿轮旁边的空白没打开设置 —— 热区判定没生效")

    def test_clicking_far_from_gear_does_not_open_settings(self):
        """离齿轮远的地方点击，不能误开设置面板。

        距离判定是「命中就开设置」，如果范围算大了，
        点标题、点副标题都会弹设置面板 —— 比点不中更烦。
        """
        opened = []
        self.app._open_settings = lambda: opened.append(True)
        gx, gy = self.app.gear_center
        far = hf.GEAR_HIT_R + 25
        self.app.cv.event_generate("<Button-1>", x=int(gx - far),
                                   y=int(gy + far))
        self.app.root.update()
        self.assertFalse(opened, "点离齿轮很远的地方也弹出了设置面板")

    def test_clicking_gear_does_not_drag_the_window(self):
        """点齿轮开设置，不该顺手把浮窗也拖走。

        点齿轮之后如果还进入拖拽逻辑，用户想点设置却把浮窗甩到了
        屏幕另一边 —— 这是「点齿轮」最典型的误伤。

        判据用标志位而不是 assert 失败：
        Tk 会把事件回调里抛出的异常吞掉（只打到 stderr），
        在 lambda 里直接 self.fail() 是测不出问题的。
        """
        dragged = []
        self.app._drag_start = lambda e: dragged.append((e.x, e.y))
        gx, gy = self.app.gear_center
        self.app.cv.event_generate("<Button-1>", x=int(gx), y=int(gy))
        self.app.root.update()
        self.assertFalse(dragged,
                         "点齿轮时启动了拖拽 —— 点齿轮不该拖动浮窗")

    def test_gear_click_returns_break_to_stop_drag(self):
        """命中齿轮时必须返回 "break"，阻断后续同级绑定。

        Tk 里同一 widget 的多个 <Button-1> 绑定是「都执行」的，
        只有返回 "break" 才能让后面的停下。
        少了这一句，点齿轮就等于同时点了「开始拖拽」——
        用户点设置，浮窗却跟着跑了。
        """
        src = _read("health_float.py")
        self.assertIn('self._open_settings()\n            return "break"',
                      src,
                      "命中齿轮后没有 return \"break\" —— "
                      "点齿轮会同时触发拖拽")

    # ---------- 文案 ----------
    def test_titles_are_four_characters_max(self):
        """标题控制在 4 个汉字以内。

        5 个字（100pt）+ emoji + 间隔 会超过文字栏内容宽，
        顶到右边缘。用户截图里「该看远方啦」就是顶出去了。
        """
        for key, (title, _sub, _icon, _, _) in hf.ALERT_META.items():
            self.assertLessEqual(
                len(title), 4,
                f"「{title}」{len(title)} 个字，太长了会撑破文字栏")

    def test_subtitle_lines_are_short(self):
        """副标题每行不超过 6 个汉字，读起来才不喘"""
        for key, (_t, sub, _i, _, _) in hf.ALERT_META.items():
            for line in sub.split("\n"):
                self.assertLessEqual(
                    len(line), 7,
                    f"「{key}」副标题行「{line}」太长（{len(line)} 字）")

    def test_subtitle_has_explicit_line_break(self):
        """副标题必须分成两行（一句一行）"""
        for key, (_t, sub, _i, _, _) in hf.ALERT_META.items():
            self.assertIn("\n", sub, f"「{key}」副标题没有换行")


class TestSingleCardNoWhitePanel(unittest.TestCase):
    """提醒卡只能有一个框 —— 白色板子不能再回来。

    背景：2026-11-13 用户第三次发截图投诉，
    「这个白色框很丑 … 放进去一整个框 … 不单独两个框」。

    旧结构是「灰底上的白板」：左边舷窗融在画布灰里，
    右边压着一块近白色 (#f4f6f9) 的圆角板子。
    一块又亮又硬的板子挤在柔和的舷窗旁边 —— 这就是「两个框」。

    现在整张卡只有一个圆角矩形（卡片底），舷窗和文字都在它里面。
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.cfg = hf.load_config()
        cls.app = hf.FloatApp(cls.root, cls.cfg)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        self.app.current = "sleep"
        self.app.auto_left = 93
        self.app._resize_to(*hf.ALERT)
        self.app._layout_alert()
        self.root.update()

    def test_no_white_panel_element_exists(self):
        """不能再有独立的白色面板元素。"""
        self.assertFalse(
            hasattr(self.app, "panel_id"),
            "又出现了独立的 panel_id —— "
            "提醒卡必须只有一张卡片，不是一个图 + 一个白板")

    def test_no_near_white_fill_in_alert_card(self):
        """提醒卡里不能出现近白色填充。

        #f4f6f9 那块白板就是「丑」的来源。
        这条按颜色拦：谁把白板加回来都会被打回。
        """
        cv = self.app.cv
        near_white = []
        for item in cv.find_all():
            if cv.itemcget(item, "state") != "normal":
                continue
            if cv.type(item) not in ("polygon", "rectangle", "oval"):
                continue
            try:
                fill = cv.itemcget(item, "fill")
            except tk.TclError:
                continue
            if not fill.startswith("#"):
                continue
            r, g, b = (int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16))
            # 近白：三个通道都很高，且彼此接近（冷白）
            if r > 235 and g > 235 and b > 235 and abs(r - b) < 12:
                near_white.append((item, fill))
        self.assertEqual(
            near_white, [],
            f"提醒卡里又出现了近白填充 {near_white} —— "
            "白色板子就是「两个框」的根源，别加回来")

    def test_card_is_the_only_container(self):
        """卡片底必须是最先创建的那一个（在所有元素之下）。

        之前那块白板是后创建的，结果它盖在舷窗图之上，
        逼得布局必须把图和文字分开放 —— 直接导致「两个框」。
        """
        cv = self.app.cv
        items = cv.find_all()
        self.assertIn(self.app.card_id, items, "卡片底没画出来")
        self.assertEqual(
            items.index(self.app.card_id), 0,
            "卡片底必须是画布上第一个元素，否则会盖住舷窗和文字")

    def test_porthole_uses_recolored_asset(self):
        """舷窗必须用换过底色的卡片素材。

        舷窗原本是画在灰底上的，直接放到暖色卡片上会露出
        一块灰色矩形 —— 又是两个框。
        """
        card_imgs = getattr(self.app, "card_images", {})
        self.assertIn(
            hf.ALERT_IMG, card_imgs,
            f"缺少卡片素材 card_{hf.ALERT_TONE}_{hf.ALERT_IMG[0]}x"
            f"{hf.ALERT_IMG[1]}.png —— "
            "舷窗会用原素材，带一块灰底出来")

    def test_porthole_asset_has_transparent_halo(self):
        """卡片素材必须有透明的外圈光晕。

        舷窗自带一圈很宽的冷调柔光晕。在灰底画布上它和底色同色系，
        看不出来；换成暖色卡片后，它就变成一块冷色方块被硬切在
        图框边缘上 —— 还是「两个框」，只是从「两块颜色」变成
        「一个框里嵌一个方块」。

        换色治不了它（光晕离背景太远，会被当成物体保留），
        只能让它淡出。所以素材必须有 alpha 通道，且四角透明。
        """
        path = os.path.join(hf.ASSETS_DIR,
                            "card_%s_%dx%d.png" % (hf.ALERT_TONE,
                                                   hf.ALERT_IMG[0],
                                                   hf.ALERT_IMG[1]))
        self.assertTrue(os.path.exists(path),
                        f"找不到卡片素材 {os.path.basename(path)}")
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 未安装，跳过素材通道检查")
        im = Image.open(path)
        self.assertIn(
            "A", im.mode,
            f"卡片素材没有 alpha 通道（mode={im.mode}）—— "
            "舷窗外圈的柔光晕会变成一块冷色方块")
        alpha = im.convert("RGBA").getchannel("A")
        lo, hi = alpha.getextrema()
        self.assertEqual(lo, 0,
                         "素材四角没有完全透明 —— 光晕边界仍然可见")
        self.assertEqual(hi, 255, "素材中心不透明 —— 舷窗本体丢了")

    def test_title_font_is_not_bold(self):
        """标题不能用粗体。

        「柔和」主要来自去掉 bold —— PingFang 的粗体很重，
        15pt 加粗中文在小卡片上像标题栏，不像提醒。
        """
        cv = self.app.cv
        font = cv.itemcget(self.app.a_title_id, "font")
        self.assertNotIn(
            "bold", font,
            f"标题又变回粗体了（{font}）—— 用 normal 权重")

    def test_alert_card_is_smaller_than_before(self):
        """提醒卡整体要比上一版小。"""
        self.assertLessEqual(hf.ALERT[0], 280, "提醒卡宽度没缩小")
        self.assertLessEqual(hf.ALERT[1], 216, "提醒卡高度没缩小")


class TestRoundRectGeometry(unittest.TestCase):
    """圆角矩形的几何守卫。

    背景：round_rect 原来用 create_polygon(smooth=True)，
    样条会在直边上「鼓包」—— 按钮顶边变成一串小台阶，
    用户截图放大后一眼就能看出那条边是波浪形的，不是一条直线。
    """

    def test_polygon_is_not_smooth(self):
        """圆角矩形不能开样条。

        smooth=True 的样条过点时会在直边中间鼓起，
        边缘看着像被手抖着画出来的。

        注意：匹配前必须剥掉注释**和 docstring** —— 解释
        「为什么不用样条」的说明里正好写着 smooth=True，
        直接 grep 会自己骗自己（这个坑踩过一次了）。
        """
        src = _read("health_float.py")
        # 只看 round_rect 函数体，别被别处的 smooth=True 带偏
        body = src.split("def round_rect(", 1)[1].split("\ndef ", 1)[0]
        # 去掉 docstring
        code = re.sub(r'"""(?:.|\n)*?"""', "", body)
        # 去掉行注释
        code = "\n".join(line.split("#", 1)[0]
                         for line in code.splitlines())
        self.assertNotIn(
            "smooth=True", code,
            "圆角矩形又用回样条多边形了 —— 直边会鼓包成波浪线")

    def test_point_count_is_constant(self):
        """点集点数必须与半径无关。

        按钮是先以 10x10 建的（r=8 > 5），之后用 cv.coords()
        换成真正的尺寸。如果点数会随半径变，coords() 换点集时
        多边形就会错乱。
        """
        counts = set()
        for r in (2, 5, 8, 12, 20):
            pts = hf.round_rect_pts(0, 0, 100, 40, r)
            counts.add(len(pts) // 2)
        self.assertEqual(
            len(counts), 1,
            f"点集点数随半径变化了（{sorted(counts)}）—— "
            "cv.coords() 换尺寸时多边形会错乱")

    def test_radius_is_clamped_to_half_of_short_side(self):
        """半径不能超过短边一半，否则圆弧自交。"""
        pts = hf.round_rect_pts(0, 0, 10, 10, 8)
        xs = [pts[i] for i in range(0, len(pts), 2)]
        ys = [pts[i + 1] for i in range(0, len(pts), 2)]
        self.assertGreaterEqual(min(xs), 0.0, "点跑到矩形左边外面了")
        self.assertLessEqual(max(xs), 10.0, "点跑到矩形右边外面了")
        self.assertGreaterEqual(min(ys), 0.0, "点跑到矩形上边外面了")
        self.assertLessEqual(max(ys), 10.0, "点跑到矩形下边外面了")

    def test_points_lie_on_the_arc(self):
        """圆角处的点必须真的落在圆上，不是直线插值。

        直边上的点可以任意分布，但每个圆角的点必须到圆心等距。
        """
        x1, y1, x2, y2, r = 10, 10, 90, 50, 12
        pts = hf.round_rect_pts(x1, y1, x2, y2, r)
        # 找右上角的圆心
        cx, cy = x2 - r, y1 + r
        # 取靠近该圆心的若干点，验证到圆心距离 == r
        near = [p for p in range(0, len(pts), 2)
                if abs(pts[p] - cx) < r and abs(pts[p + 1] - cy) < r]
        self.assertGreater(len(near), 4, "右上角附近没有采样点")
        for p in near[:3]:
            d = ((pts[p] - cx) ** 2 + (pts[p + 1] - cy) ** 2) ** 0.5
            self.assertAlmostEqual(
                d, r, places=1,
                msg=f"圆角采样点不在圆上（距离 {d:.2f}，应为 {r}）")

    def test_rounding_step_count_is_enough(self):
        """圆弧采样不能太少，否则圆角看着像倒角。"""
        self.assertGreaterEqual(
            hf.ARC_STEPS, 10,
            "圆弧采样点太少 —— 圆角会看着像斜切角而不是圆弧")


if __name__ == "__main__":
    unittest.main(verbosity=2)
