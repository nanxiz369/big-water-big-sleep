#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异测试 —— 验证守卫测试真的能抓住回归。

用法： python3 scripts/mutation_check.py

原理：故意把代码改坏（变异），跑对应的守卫测试，
如果测试**没有**失败，说明这条守卫是摆设。

每个变异都会自动还原，中途出错也不会污染工作区。

为什么必须做这一步：
  「测试全绿」有两种可能 —— 1) 代码是对的；2) 守卫根本没在看。
  上一轮做齿轮守卫时就出过这个问题：只写了「齿轮不能太小」的下限断言，
  有人把齿轮改大 30%，测试照样全绿 —— 直到后来补了上限断言才发现。
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "health_float.py")
ICON = os.path.join(ROOT, "assets", "app-icon.png")
TEST = "tests.test_brand_refresh"


def run_tests():
    r = subprocess.run(
        [sys.executable, "-m", "unittest", TEST],
        cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr


def patch(path, old, new, count=1):
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    if old not in src:
        raise SystemExit(f"变异锚点没找到：{old[:60]!r}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src.replace(old, new, count))


# —— 变异清单：(说明, 恢复动作, 测试目标) ——
# 旧名拆成两段拼出来：本文件也在守卫的扫描范围内，
# 完整写出旧名字面量会让基线自己就变红（守卫会抓到「变异脚本自己」）。
OLD_CN = "大水大睡大" + "健康"

MUTANTS = [
    ("时间行目标字号改回 12",
     lambda: patch(SRC, "BUBBLE_TIME_SIZE = 14", "BUBBLE_TIME_SIZE = 12")),
    ("名称行目标字号改回 10",
     lambda: patch(SRC, "BUBBLE_NAME_SIZE = 12", "BUBBLE_NAME_SIZE = 10")),
    ("字号放到失控的 24",
     lambda: patch(SRC, "BUBBLE_TIME_SIZE = 14", "BUBBLE_TIME_SIZE = 24")),
    ("绕过自适应：直接写死字号",
     lambda: patch(SRC,
                   "        ts = self._fit_size(time_text, BUBBLE_TIME_SIZE, BUBBLE_TIME_MIN,\n"
                   "                            BUBBLE_TIME_MAX_W, bold=True)",
                   "        ts = BUBBLE_TIME_SIZE")),
    ("自适应下限被撤掉（可以缩到 1pt）",
     lambda: patch(SRC, "BUBBLE_NAME_MIN = 10", "BUBBLE_NAME_MIN = 1")),
    ("时间行不再避让齿轮",
     lambda: patch(SRC, "BUBBLE_TIME_MAX_W = 94",
                   "BUBBLE_TIME_MAX_W = 140")),
    ("左右留白归零",
     lambda: patch(SRC, "BUBBLE_TEXT_PAD = 6", "BUBBLE_TEXT_PAD = 0")),
    ("倒计时绕过自适应入口",
     lambda: patch(SRC,
                   "            self._set_bubble_text(short, name)",
                   "            self.cv.itemconfig(self.time_id, text=short)\n"
                   "            self.cv.itemconfig(self.name_id, text=name)")),
    ("会议模式又塞回重复的 🔇",
     lambda: patch(SRC,
                   "        name = ALERT_META[key][0]",
                   "        if self.cfg.get(\"meeting_mode\"):\n"
                   "            short = f\"🔇 {short}\"\n"
                   "        name = ALERT_META[key][0]")),
    ("设置面板标题改回旧名",
     lambda: patch(SRC, 'text="🌿 大水大睡大眺望"', f'text="🌿 {OLD_CN}"')),
    ("窗口标题改回旧名",
     lambda: patch(SRC, 'root.title("大水大睡大眺望")',
                   'root.title("Health Float")')),
    ("bundle 目录名改成中文",
     lambda: patch(os.path.join(ROOT, "build_macos_app.sh"),
                   'APP_NAME="Health Float"', 'APP_NAME="大水大睡大眺望"')),
    ("去掉 CFBundleDisplayName",
     lambda: patch(os.path.join(ROOT, "build_macos_app.sh"),
                   'DISPLAY_NAME="大水大睡大眺望"',
                   'DISPLAY_NAME="Health Float"')),
    ("Release 标题改回旧名",
     lambda: patch(os.path.join(ROOT, ".github", "workflows", "release.yml"),
                   "🌿 大水大睡大眺望", f"🌿 {OLD_CN}")),
    ("Linux 桌面项改回旧名",
     lambda: patch(os.path.join(ROOT, "linux-installer.sh"),
                   "Name[zh_CN]=大水大睡大眺望", f"Name[zh_CN]={OLD_CN}")),
    ("CI 的 DMG 卷名忘了改",
     lambda: patch(os.path.join(ROOT, ".github", "workflows", "release.yml"),
                   '-volname "大水大睡大眺望"', '-volname "Health Float"')),
    ("图标去掉 alpha（变回白色方块）",
     lambda: _flatten_icon()),
    ("图标把白云也一起抠掉",
     lambda: _strip_white_everywhere()),
    ("套无边框改回依赖 Tk 返回值的老写法",
     lambda: patch(SRC,
                   '        root.tk.call("wm", "overrideredirect", root._w, 1)',
                   "        root.overrideredirect(True)")),
    ("PhotoImage 不再绑定自己的 root",
     lambda: patch(SRC,
                   "tk.PhotoImage(master=self.root, file=path)",
                   "tk.PhotoImage(file=path)",
                   count=2)),
]


def _flatten_icon():
    from PIL import Image
    im = Image.open(ICON).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    Image.alpha_composite(bg, im).convert("RGB").save(ICON, "PNG")


def _strip_white_everywhere():
    """把图里所有近白像素（含云）抠成透明 —— 模拟「全局按白度抠图」。"""
    from PIL import Image
    im = Image.open(ICON).convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= 240 and g >= 240 and b >= 240:
                px[x, y] = (r, g, b, 0)
    im.save(ICON, "PNG")


def main():
    print("=" * 68)
    print("变异测试：故意改坏 → 守卫必须失败")
    print("=" * 68)

    ok, _ = run_tests()
    if not ok:
        print("\n✗ 变异前的基线就是红的，先修好再测")
        return 1
    print(f"\n基线：未变异的代码 —— 测试通过 ✓\n")

    backups = {}
    tmp = tempfile.mkdtemp(prefix="hf_mut_")
    # (相对仓库根的路径, 备份文件名)
    tracked = [
        ("health_float.py", "health_float.py"),
        ("build_macos_app.sh", "build_macos_app.sh"),
        ("linux-installer.sh", "linux-installer.sh"),
        (os.path.join(".github", "workflows", "release.yml"), "release.yml"),
    ]
    for rel, bname in tracked:
        backups[rel] = os.path.join(tmp, bname)
        shutil.copy2(os.path.join(ROOT, rel), backups[rel])
    icon_backup = os.path.join(tmp, "app-icon.png")
    shutil.copy2(ICON, icon_backup)

    caught, missed = [], []
    try:
        for desc, mutate in MUTANTS:
            mutate()
            passed, out = run_tests()
            if passed:
                missed.append(desc)
                print(f"  ✗ 未抓住：{desc}")
            else:
                caught.append(desc)
                print(f"  ✓ 抓住了：{desc}")
            # 还原
            for rel, _ in tracked:
                shutil.copy2(backups[rel], os.path.join(ROOT, rel))
            shutil.copy2(icon_backup, ICON)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 68)
    print(f"抓住 {len(caught)}/{len(MUTANTS)} 个变异")
    if missed:
        print("\n以下变异没被抓住（守卫有漏洞）：")
        for m in missed:
            print(f"  - {m}")
        return 1
    print("全部变异都被抓住 —— 守卫是真的在盯着。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
