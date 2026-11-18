#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「品牌焕新」守卫测试 —— 2026-11-18

一轮改动三件事，每件都对应用户明确提的要求：

  1. 泡泡文字放大（时间 12→14，名称 10→12）
  2. 应用图标换成「眺远方」新图
  3. 应用改名「大水大睡大眺望」

每个用例都对应一个**真实会发生的回归**，不是覆盖率凑数：

  · 字号改回小值 → 用户明确说过要放大，不能被悄悄改回去
  · 放大后最长的文案冲出画布 → 「看看远方 · 准备一下」在 12pt 下要 144pt，
    而泡泡只有 140pt 宽；这是本轮改动的核心难点，必须守住
  · 图标变成没有透明圆角的白方块 → 新图是 RGB 无 alpha，
    直接拷进去在 macOS 上就是一个白色方块
  · 图标把白云一起抠掉 → 抠图只能动外圈，不能按饱和度全局抠
  · 名字只改了一半 → Dock 显示旧名、设置面板显示新名，比不改还乱

运行： python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest
import ast

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _utf8_console  # noqa: F401,E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk  # noqa: E402
import tkinter.font as tkfont  # noqa: E402

import health_float as hf  # noqa: E402
from png_reader import (alpha_at, count_opaque_near_white,  # noqa: E402
                        read_png, rgb_at)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(ROOT_DIR, "assets", "app-icon.png")

# 产品名。中文显示名 = 大水大睡大眺望；ASCII 文件名 = Health Float。
PRODUCT_CN = "大水大睡大眺望"
PRODUCT_OLD_CN = "大水大睡大健康"
PRODUCT_ASCII = "Health Float"


def _read(rel_path):
    with open(os.path.join(ROOT_DIR, rel_path), "r", encoding="utf-8") as fh:
        return fh.read()


def _calls_in_function(src, func_name):
    """列出某个函数里所有的方法调用：(接收者表达式, 方法名)。

    用 AST 而不是文本匹配 —— 文本匹配会把 docstring 里
    「不能直接写 root.overrideredirect(True)」这类说明当成真调用。
    """
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == func_name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) \
                        and isinstance(sub.func, ast.Attribute):
                    recv = ast.unparse(sub.func.value)
                    out.append((recv, sub.func.attr))
    return out


def _all_overrideredirect_calls(src):
    """列出文件里所有**带参数**的 .overrideredirect(...) 调用。

    只看设置调用（overrideredirect(True)）——
    无参的读取调用（overrideredirect()）是查状态，
    它在 _ensure_borderless 里已被 try/except 包住，是安全的。

    返回：(所在函数名, 行号)。
    """
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) \
                        and isinstance(sub.func, ast.Attribute) \
                        and sub.func.attr == "overrideredirect" \
                        and sub.args:
                    out.append((node.name, sub.lineno))
    return out


class TestBubbleTypography(unittest.TestCase):
    """泡泡文字：放大 + 放大后不破版。"""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        # 显示但全透明 —— withdraw() 的窗口收不到事件。
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
        except Exception:
            pass

    def _font_of(self, item_id):
        spec = self.app.cv.itemcget(item_id, "font")
        return tkfont.Font(root=self.app.root, font=spec)

    def _size_of(self, item_id):
        """读图元当前的实际字号。

        tkfont.Font 没有 .size() 方法 —— 得走 actual("size")。
        """
        return self._font_of(item_id).actual("size")

    # —— 目标字号不许被改小，也不许再往上冲 ——

    def test_time_row_target_size_is_the_middle_ground(self):
        """时间行目标字号必须落在 13~14。

        上一版是 12，用户说「大一点点」→ 我放到 14，
        用户看了预览说「稍微有点大了，就在这个和上一版的中间」→ 13。
        这个区间就是用户拍板的那一档，不许再漂移。
        """
        self.assertGreaterEqual(
            hf.BUBBLE_TIME_SIZE, 13,
            f"时间行目标字号退回 {hf.BUBBLE_TIME_SIZE}pt 了 —— "
            f"用户明确要求放大",
        )
        self.assertLessEqual(
            hf.BUBBLE_TIME_SIZE, 14,
            f"时间行目标字号涨到 {hf.BUBBLE_TIME_SIZE}pt 了 —— "
            f"用户明确说过这一档偏大",
        )

    def test_name_row_target_size_is_the_middle_ground(self):
        """名称行目标字号必须落在 11~12（上一版是 10）。"""
        self.assertGreaterEqual(
            hf.BUBBLE_NAME_SIZE, 11,
            f"名称行目标字号退回 {hf.BUBBLE_NAME_SIZE}pt 了",
        )
        self.assertLessEqual(
            hf.BUBBLE_NAME_SIZE, 12,
            f"名称行目标字号涨到 {hf.BUBBLE_NAME_SIZE}pt 了 —— "
            f"用户明确说过这一档偏大",
        )

    def test_target_sizes_are_not_absurd(self):
        """兜底上限 —— 放到 24pt 会把画布撑爆。"""
        self.assertLessEqual(hf.BUBBLE_TIME_SIZE, 18)
        self.assertLessEqual(hf.BUBBLE_NAME_SIZE, 16)

    # —— 放大后的实际落点 ——

    def test_normal_state_uses_the_increased_sizes(self):
        """最常见的场景（正常倒计时）必须真的用上放大后的字号。"""
        self.app._set_bubble_text("15 分40秒", "看看远方")
        self.assertEqual(self._size_of(self.app.time_id), 13)
        self.assertEqual(self._size_of(self.app.name_id), 11)

    def test_short_countdown_keeps_the_large_time_size(self):
        """秒级倒计时（'30 秒'）也应该是 13pt。"""
        self.app._set_bubble_text("30 秒", "看看远方")
        self.assertEqual(self._size_of(self.app.time_id), 13)

    def test_normal_time_row_keeps_clear_space_from_the_gear(self):
        """常态下时间行和齿轮之间要留得出呼吸的间隙。

        14pt 时「秒」字几乎贴着齿轮（间隙 4.8pt），
        13pt 时回到 9.3pt —— 这正是用户说 14pt「有点大」的实拍理由。
        """
        gear_left = (hf.BUBBLE[0] - 17) - hf.GEAR_R
        self.app._set_bubble_text("19 分58秒", "看看远方")
        fnt = self._font_of(self.app.time_id)
        right_edge = hf.BUBBLE[0] / 2 + fnt.measure("19 分58秒") / 2
        self.assertGreaterEqual(
            gear_left - right_edge, 8,
            f"时间行右缘 {right_edge:.1f} 离齿轮左缘 {gear_left:.1f} "
            f"只剩 {gear_left - right_edge:.1f}pt —— 挤",
        )

    # —— 核心难点：放大后不能破版 ——

    def test_longest_label_still_fits_inside_the_canvas(self):
        """「看看远方 · 准备一下」是最长的一句。

        12pt 下它要 144pt，而泡泡只有 140pt 宽 ——
        不做自适应降级就会直接冲出画布。
        """
        text = "看看远方 · 准备一下"
        self.app._set_bubble_text("15 分40秒后", text)
        width = self._font_of(self.app.name_id).measure(text)
        self.assertLessEqual(
            width, hf.BUBBLE[0],
            f"名称行宽 {width}pt 超出泡泡宽 {hf.BUBBLE[0]}pt —— 会冲出画布",
        )

    def test_every_alert_name_fits_at_target_size(self):
        """所有事件名在目标字号下都要放得进画布。"""
        for key, meta in hf.ALERT_META.items():
            name = meta[0]
            width = self._font_of(self.app.name_id).measure(name) \
                if self.app.name_id else 0
            fnt = tkfont.Font(root=self.app.root,
                              font=hf.ui_font(hf.BUBBLE_NAME_SIZE))
            self.assertLessEqual(
                fnt.measure(name), hf.BUBBLE_NAME_MAX_W,
                f"事件「{name}」在 {hf.BUBBLE_NAME_SIZE}pt 下超出可用宽度",
            )

    def test_time_row_stays_clear_of_the_gear(self):
        """时间行的字底会擦到齿轮顶，不能压上去。

        齿轮本体左缘 = 中心(w-17) - GEAR_R。
        """
        gear_left = (hf.BUBBLE[0] - 17) - hf.GEAR_R
        for text in ("15 分40秒", "15 分40秒后", "59 分59秒"):
            self.app._set_bubble_text(text, "看看远方")
            fnt = self._font_of(self.app.time_id)
            right_edge = hf.BUBBLE[0] / 2 + fnt.measure(text) / 2
            self.assertLessEqual(
                right_edge, gear_left,
                f"时间行「{text}」右缘 {right_edge:.1f} 压到齿轮左缘 {gear_left:.1f}",
            )

    def test_fit_size_never_exceeds_max_width(self):
        """_fit_size 的契约：返回的字号必须真的放得下。

        时间行和名称行各有自己的文案与宽度约束，不能混着测。
        """
        cases = [
            (("15 分40秒", "15 分40秒后", "30 秒", "59 分59秒"),
             hf.BUBBLE_TIME_SIZE, hf.BUBBLE_TIME_MIN,
             hf.BUBBLE_TIME_MAX_W, True),
            (("看看远方", "看看远方 · 准备一下", "双击可设置提醒", "起来动动"),
             hf.BUBBLE_NAME_SIZE, hf.BUBBLE_NAME_MIN,
             hf.BUBBLE_NAME_MAX_W, False),
        ]
        for texts, base, lo, maxw, bold in cases:
            for text in texts:
                size = self.app._fit_size(text, base, lo, maxw, bold)
                fnt = tkfont.Font(root=self.app.root,
                                  font=hf.ui_font(size, bold))
                self.assertLessEqual(
                    fnt.measure(text), maxw,
                    f"_fit_size 返回 {size}pt，但「{text}」宽 "
                    f"{fnt.measure(text)} > {maxw}",
                )

    def test_fit_size_never_goes_below_the_floor(self):
        """字号下限必须守住 —— 再小就完全看不见了。

        断言的是**绝对值**而不是 hf.BUBBLE_NAME_MIN ——
        如果只断言「返回值 >= 常量」，把常量本身改成 1 就等于没断言。
        """
        size = self.app._fit_size("很长很长很长很长很长很长",
                                  hf.BUBBLE_NAME_SIZE, hf.BUBBLE_NAME_MIN,
                                  hf.BUBBLE_NAME_MAX_W)
        self.assertGreaterEqual(size, 9,
                                f"字号降到 {size}pt 了 —— 文字会看不清")

    def test_size_floors_are_absolute(self):
        """下限常量本身也要有绝对下限。"""
        self.assertGreaterEqual(hf.BUBBLE_NAME_MIN, 10,
                                "名称行字号下限被撤了")
        self.assertGreaterEqual(hf.BUBBLE_TIME_MIN, 10,
                                "时间行字号下限被撤了")

    # —— 实现层面的约束 ——

    def test_countdown_goes_through_the_adaptive_setter(self):
        """_update_countdown 的**每一条路径**都必须走 _set_bubble_text。

        只断言「函数体里出现过 _set_bubble_text」是不够的 ——
        变异掉其中一条路径后，另一条还在，字符串照样存在，断言照样通过。
        所以这里数调用次数（空态 / prewarn / 正常，共 3 处），
        并额外禁止函数体里出现直接写 text 的 itemconfig。
        """
        src = _read("health_float.py")
        body = src.split("def _update_countdown")[1].split("def ")[0]
        self.assertEqual(
            body.count("_set_bubble_text("), 3,
            "_update_countdown 里 _set_bubble_text 的调用次数不是 3 —— "
            "有路径绕过了自适应（破版入口）",
        )
        self.assertNotIn(
            "itemconfig(self.time_id, text=", body,
            "_update_countdown 直接写 text —— 绕过了字号自适应",
        )
        self.assertNotIn(
            "itemconfig(self.name_id, text=", body,
            "_update_countdown 直接写 text —— 绕过了字号自适应",
        )

    def test_meeting_mode_does_not_double_the_mute_icon(self):
        """会议模式不再往时间文本里塞 🔇。

        泡泡左上角已经有一个橙色静音指示图元了（mute_id），
        两个 🔇 同时出现是重复，而且 emoji 偏宽会把时间行挤到齿轮上。
        """
        src = _read("health_float.py")
        body = src.split("def _update_countdown")[1].split("def ")[0]
        self.assertNotIn(
            '🔇 {short}', body,
            "会议模式又把 🔇 塞回时间文本了 —— 会和左上角的静音指示重复",
        )
        self.assertIn("mute_id", src)

    def test_bubble_text_padding_is_positive(self):
        """左右留白必须是正数，否则文字会贴到画布边上。"""
        self.assertGreater(hf.BUBBLE_TEXT_PAD, 0)
        self.assertLess(hf.BUBBLE_NAME_MAX_W, hf.BUBBLE[0])


class TestIconAsset(unittest.TestCase):
    """图标：必须是带透明圆角的 RGBA，云还得在。"""

    @classmethod
    def setUpClass(cls):
        cls.width, cls.height, cls.channels, cls.rows = read_png(ICON_PATH)

    def test_icon_file_exists(self):
        self.assertTrue(os.path.exists(ICON_PATH),
                        "assets/app-icon.png 缺失 —— 构建期就依赖它")

    def test_icon_is_rgba(self):
        """必须是 RGBA（channels=4）。

        RGB 图（没有 alpha 通道）在 macOS 上会显示成一个白色方块 ——
        新图「眺远方」原图正是 RGB，这是本轮最容易踩的坑。
        """
        self.assertEqual(
            self.channels, 4,
            "图标没有 alpha 通道 —— macOS 上会变成白色方块。"
            "用 scripts/apply_icon.py 重新生成",
        )

    def test_icon_corners_are_transparent(self):
        """四个角必须透明 —— 透明圆角是 macOS 图标的基本要求。"""
        w, h = self.width, self.height
        corners = [
            alpha_at(self.rows, w, self.channels, 0, 0),
            alpha_at(self.rows, w, self.channels, w - 1, 0),
            alpha_at(self.rows, w, self.channels, 0, h - 1),
            alpha_at(self.rows, w, self.channels, w - 1, h - 1),
        ]
        self.assertTrue(
            all(a < 40 for a in corners),
            f"四角 alpha={corners} —— 不是全透明，图标会被裁成圆角以外的方块",
        )

    def test_icon_center_is_opaque(self):
        w, h = self.width, self.height
        a = alpha_at(self.rows, w, self.channels, w // 2, h // 2)
        self.assertEqual(a, 255, "图标中心应该是完全不透明的")

    def test_icon_edges_are_opaque(self):
        """边的中点不透明 —— 角是透明的、边是实的，才是圆角形状。"""
        w, h = self.width, self.height
        edges = [
            alpha_at(self.rows, w, self.channels, 1, h // 2),
            alpha_at(self.rows, w, self.channels, w - 2, h // 2),
            alpha_at(self.rows, w, self.channels, w // 2, 1),
            alpha_at(self.rows, w, self.channels, w // 2, h - 2),
        ]
        self.assertTrue(all(a > 200 for a in edges),
                        f"边中点 alpha={edges} —— 圆角被啃掉了太多")

    def test_white_cloud_is_still_inside_the_icon(self):
        """白云必须还在。

        抠图只能动外圈：如果按饱和度全局抠，白云会跟着白底一起被抠掉，
        图标就少了一块最重要的元素。
        """
        count = count_opaque_near_white(self.rows, self.width, self.height,
                                         self.channels)
        self.assertGreater(
            count, 1000,
            f"图里只剩 {count} 个近白不透明像素 —— 白云多半被抠掉了",
        )

    def test_icon_is_square_and_big_enough(self):
        """接近正方形，且边长足够（1024 左右）。"""
        w, h = self.width, self.height
        self.assertGreaterEqual(w, 900, f"图标太小：{w}x{h}")
        self.assertGreaterEqual(h, 900, f"图标太小：{w}x{h}")
        self.assertLess(
            abs(w - h), 8,
            f"图标不是正方形：{w}x{h} —— 构建脚本会拉伸成方块",
        )

    def test_icon_contains_the_new_artwork(self):
        """图标里必须有新图的颜色：天空蓝、草地绿、太阳黄。

        防止「换了张别的图」或者「抠图时把内容也抠没了」。
        """
        w, h = self.width, self.height
        seen = {"sky": False, "grass": False, "sun": False}
        for y in range(0, h, 7):
            for x in range(0, w, 7):
                r, g, b = rgb_at(self.rows, w, self.channels, x, y)
                if b > r + 25 and b > 200:              # 天空蓝
                    seen["sky"] = True
                elif g > r + 35 and g > b + 35:         # 草地绿
                    seen["grass"] = True
                elif r > 200 and g > 160 and b < 150:   # 太阳黄
                    seen["sun"] = True
        for key, ok in seen.items():
            self.assertTrue(ok, f"图标里找不到「{key}」的颜色 —— 画面对不上")

    def test_apply_icon_script_exists_and_is_documented(self):
        """生成脚本要在仓库里 —— 下次换图还得靠它。"""
        path = os.path.join(ROOT_DIR, "scripts", "apply_icon.py")
        self.assertTrue(os.path.exists(path),
                        "scripts/apply_icon.py 缺失 —— 换图标会退回手工处理")
        src = _read(os.path.join("scripts", "apply_icon.py"))
        self.assertIn("alpha", src.lower())
        self.assertIn("trim_transparent_border", src,
                      "脚本必须只抠外圈（内部的白云要保留）")


class TestTkRobustness(unittest.TestCase):
    """Tk 的两个脆弱点 —— 都是 CI 抓出来的真 bug。

    这两条不是「顺手加的健壮性」，是实际会让用户遇到「应用启动即崩」
    或「窗口显示异常」的坑，必须有守卫盯着不许改回去。
    """

    def test_borderless_does_not_depend_on_tk_return_value(self):
        """套无边框不能依赖 `wm overrideredirect` 的返回值。

        tkinter 的 wm_overrideredirect 会把返回值交给 _getboolean()，
        而某些环境下 Tk 返回的是空字符串 —— _getboolean("") 直接抛
        TclError。表现是应用刚启动就崩。
        """
        calls = _calls_in_function(_read("health_float.py"), "_set_borderless")
        attrs = [c for c in calls if c[1] == "overrideredirect"]
        self.assertEqual(
            attrs, [],
            "_set_borderless 里不能调 overrideredirect —— "
            "它会因 Tk 返回空字符串而抛 TclError",
        )
        tk_calls = [c for c in calls if c[1] == "call"]
        self.assertTrue(
            tk_calls,
            "_set_borderless 必须用 tk.call 发命令，绕开返回值转换",
        )

    def test_no_bare_overrideredirect_call_remains(self):
        """整个文件里不能有裸的 .overrideredirect(...) 调用。

        用 AST 检查而不是文本匹配 —— 文本匹配会误伤 docstring 里
        「为什么不能直接写 root.overrideredirect(True)」这类说明。
        """
        src = _read("health_float.py")
        offenders = []
        for name, lineno in _all_overrideredirect_calls(src):
            if name == "_set_borderless":
                continue
            offenders.append(f"第 {lineno} 行 {name}()")
        self.assertEqual(
            offenders, [],
            f"还有裸的 overrideredirect 调用：{offenders}\n请改用 _set_borderless()",
        )

    def test_photo_images_are_bound_to_their_own_root(self):
        """PhotoImage 必须指定 master=self.root。

        不指定的话图片会绑定到 tkinter 的「默认 root」，
        而不是浮窗自己的 root。一旦进程里存在多个 Tk interpreter
        （测试环境、或将来任何多窗口场景），canvas 引用到的就是
        另一个 interpreter 的图片名，报 "pyimage11 doesn't exist"。
        """
        src = _read("health_float.py")
        self.assertNotIn(
            "tk.PhotoImage(file=", src,
            "PhotoImage 没有指定 master —— 跨 Tk interpreter 时图片名会串",
        )
        self.assertIn("tk.PhotoImage(master=self.root, file=path)", src)

    def test_borderless_helper_returns_a_bool(self):
        """_set_borderless 必须给出明确成败，不能默默吞异常。"""
        root = tk.Tk()
        root.withdraw()
        try:
            self.assertIsInstance(hf._set_borderless(root), bool)
        finally:
            root.destroy()

    def test_borderless_helper_survives_a_broken_root(self):
        """root 坏掉时不能抛异常 —— 巡检是后台任务，抛了就停了。"""
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        try:
            result = hf._set_borderless(root)
        except Exception as e:                      # noqa: BLE001
            self.fail(f"_set_borderless 对坏掉的 root 抛了异常：{e}")
        self.assertFalse(result)

    def test_borderless_survives_when_tk_returns_empty_string(self):
        """复现 CI 上那个真实的崩溃。

        `wm overrideredirect` 在某些环境返回空字符串 →
        tkinter 的 `_getboolean("")` 抛 TclError →
        应用刚启动就崩。

        这里用一个「一调 overrideredirect 就炸」的假 root 来模拟，
        验证 _set_borderless 走的是 tk.call 而不是 overrideredirect。
        """
        real = tk.Tk()
        real.withdraw()
        try:
            class FakeRoot:
                def __init__(self, r):
                    self._r = r
                    self.tk = r.tk
                    self._w = r._w

                def overrideredirect(self, *a):
                    raise tk.TclError('expected boolean value but got ""')

            fake = FakeRoot(real)

            # 旧写法在这个环境下必崩 —— 先确认模拟是有效的
            with self.assertRaises(tk.TclError):
                fake.overrideredirect(True)

            # 新写法必须扛住
            try:
                result = hf._set_borderless(fake)
            except Exception as e:                  # noqa: BLE001
                self.fail(f"_set_borderless 没扛住空返回值：{e}")
            self.assertTrue(result, "新写法应该成功套上无边框")
        finally:
            real.destroy()

    def test_borderless_actually_takes_effect_on_a_real_root(self):
        """不是「不报错」就算过 —— 无边框必须真的生效。"""
        root = tk.Tk()
        root.withdraw()
        try:
            hf._set_borderless(root)
            self.assertTrue(root.overrideredirect(),
                            "无边框没有真正生效")
        finally:
            root.destroy()


class TestProductName(unittest.TestCase):
    """名字：显示名全改，ASCII 文件名保持。"""

    def test_old_name_is_gone_from_source(self):
        self.assertNotIn(PRODUCT_OLD_CN, _read("health_float.py"))

    def test_old_name_is_gone_from_the_whole_repo(self):
        """除了开发笔记（历史记录）之外，不能有任何残留。

        漏改一处的后果是「Dock 显示旧名、设置面板显示新名」，
        比完全不改更让人困惑。
        """
        offenders = []
        for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
            dirnames[:] = [d for d in dirnames
                           if d not in (".git", "__pycache__", ".build",
                                        "dist", "build")]
            for fn in filenames:
                if not fn.endswith((".py", ".sh", ".bat", ".md", ".command",
                                    ".plist", ".yml", ".yaml", ".txt")):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT_DIR)
                if rel == os.path.join("docs", "开发笔记.md"):
                    continue          # 历史记录，保留原文
                if os.path.basename(full) == os.path.basename(__file__):
                    continue          # 本文件里故意留着旧名当检测样本
                try:
                    with open(full, "r", encoding="utf-8") as fh:
                        if PRODUCT_OLD_CN in fh.read():
                            offenders.append(rel)
                except (UnicodeDecodeError, OSError):
                    continue
        self.assertEqual(
            offenders, [],
            f"这些文件里还有旧名「{PRODUCT_OLD_CN}」：{offenders}",
        )

    def test_settings_dialog_title_uses_the_new_name(self):
        src = _read("health_float.py")
        self.assertIn(f'"{PRODUCT_CN} 设置"', src)
        self.assertIn(f'text="🌿 {PRODUCT_CN}"', src)

    def test_window_title_uses_the_new_name(self):
        src = _read("health_float.py")
        self.assertIn(f'root.title("{PRODUCT_CN}")', src)

    def test_readme_headline_uses_the_new_name(self):
        readme = _read("README.md")
        self.assertIn(PRODUCT_CN, readme)
        self.assertNotIn(PRODUCT_OLD_CN, readme)

    def test_linux_desktop_zh_name(self):
        src = _read("linux-installer.sh")
        self.assertIn(f"Name[zh_CN]={PRODUCT_CN}", src)

    def test_macos_display_name_is_configured(self):
        """macOS 的 Dock / Finder 显示名来自 CFBundleDisplayName。"""
        src = _read("build_macos_app.sh")
        self.assertIn(f'DISPLAY_NAME="{PRODUCT_CN}"', src)
        self.assertIn("CFBundleDisplayName", src)

    def test_macos_dmg_volume_uses_the_display_name(self):
        """DMG 卷名是用户双击后看到的东西，也应该是中文。"""
        src = _read("build_macos_app.sh")
        self.assertIn('-volname "$DISPLAY_NAME"', src)

    def test_release_workflow_dmg_volume_uses_the_display_name(self):
        """CI 打的 DMG 卷名也要是中文名。

        上一轮就踩过「本地脚本和 CI 脚本不一致」的坑 ——
        只改本地 build_macos_app.sh 而忘了 CI 里的 hdiutil，
        就会出现「本地卷名中文、用户下载下来的卷名还是英文」。
        """
        src = _read(os.path.join(".github", "workflows", "release.yml"))
        self.assertIn(
            f'-volname "{PRODUCT_CN}"', src,
            "Release workflow 里的 DMG 卷名没改成中文名 —— "
            "会跟本地 build_macos_app.sh 不一致",
        )

    def test_release_body_mentions_the_display_name_in_login_items(self):
        """登录项里显示的是 CFBundleDisplayName，说明文字要跟着改。

        否则用户按说明去找「Health Float.app」根本找不到 ——
        列表里写的是「大水大睡大眺望」。
        """
        src = _read(os.path.join(".github", "workflows", "release.yml"))
        self.assertIn(f"登录项 → 添加「{PRODUCT_CN}」", src)

    def test_filesystem_name_stays_ascii(self):
        """bundle 目录名必须保持 ASCII。

        中文 bundle 名会一路带进 PyInstaller 的 --name、DMG、
        AppImage 目录 —— 中文 exe / 目录名在 Windows 和 Linux 上
        有一堆坑（杀软误报、路径编码、appimagetool 对非 ASCII 敏感）。
        显示名的活儿交给 CFBundleDisplayName 就够了。
        """
        src = _read("build_macos_app.sh")
        self.assertIn(f'APP_NAME="{PRODUCT_ASCII}"', src)
        self.assertNotRegex(
            src, r'APP_NAME="[^"\x00-\x7f][^"]*"',
            "APP_NAME 含非 ASCII 字符 —— bundle 目录名必须是 ASCII",
        )

    def test_windows_build_keeps_ascii_exe_name(self):
        src = _read("build_windows.sh")
        self.assertIn(f'--name "{PRODUCT_ASCII}"', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
