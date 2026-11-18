#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简 PNG 读取器 —— 只为测试用，零第三方依赖。

为什么不用 Pillow：
  CI 只装了 requirements.txt（customtkinter），没有 Pillow。
  而 Pillow 被**故意**排除在打包产物之外 —— 它的编译扩展是单架构的，
  正是 universal2 构建失败的元凶（见 tests/test_packaging.py）。

  所以「图标必须是带透明圆角的 RGBA」这条守卫如果依赖 Pillow，
  在 CI 上就等于没有 —— 恰恰是最需要它的地方失效。

  zlib 是标准库，PNG 的解码用 zlib + 几十行反滤波就够。

支持范围（够用即可，遇到不支持的格式明确报错，不猜）：
  - 8 bit/channel
  - color type 2 (RGB) / 6 (RGBA)
  - 非隔行（interlace = 0）
"""

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngError(Exception):
    """PNG 解析失败。"""


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(data, width, height, bpp):
    """反滤波扫描行，返回逐行的原始像素字节。"""
    stride = width * bpp
    expected = (stride + 1) * height
    if len(data) != expected:
        raise PngError(
            f"像素数据长度异常：期望 {expected}，实际 {len(data)}")

    out = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ft = data[pos]
        pos += 1
        line = bytearray(data[pos:pos + stride])
        pos += stride

        if ft == 0:                                  # None
            pass
        elif ft == 1:                                # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:                                # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:                                # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:                                # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                ul = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], ul)) & 0xFF
        else:
            raise PngError(f"未知的行过滤类型：{ft}")

        out.append(bytes(line))
        prev = line
    return out


def read_png(path):
    """读 PNG，返回 (width, height, channels, rows)。

    rows 是 list[bytes]，每行 width*channels 个字节（RGBA 或 RGB）。
    """
    with open(path, "rb") as fh:
        blob = fh.read()

    if not blob.startswith(PNG_SIGNATURE):
        raise PngError("不是 PNG 文件（签名不对）")

    pos = len(PNG_SIGNATURE)
    idat = bytearray()
    width = height = channels = None
    bitdepth = colortype = interlace = None

    while pos < len(blob):
        if pos + 8 > len(blob):
            break
        length = struct.unpack(">I", blob[pos:pos + 4])[0]
        ctype = blob[pos + 4:pos + 8]
        data = blob[pos + 8:pos + 8 + length]
        pos += 12 + length                     # length + type + data + crc

        if ctype == b"IHDR":
            (width, height, bitdepth, colortype,
             _comp, _filt, interlace) = struct.unpack(">IIBBBBB", data)
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break

    if width is None:
        raise PngError("缺少 IHDR")
    if bitdepth != 8:
        raise PngError(f"只支持 8 bit，实际 {bitdepth}")
    if interlace != 0:
        raise PngError("不支持隔行 PNG")
    if colortype == 2:
        channels = 3
    elif colortype == 6:
        channels = 4
    else:
        raise PngError(f"只支持 RGB/RGBA，color type={colortype}")

    raw = zlib.decompress(bytes(idat))
    rows = _unfilter(raw, width, height, channels)
    return width, height, channels, rows


def alpha_at(rows, width, channels, x, y):
    """取 (x, y) 的 alpha；RGB 图（无 alpha 通道）返回 255。"""
    row = rows[y]
    i = x * channels
    if channels == 4:
        return row[i + 3]
    return 255


def rgb_at(rows, width, channels, x, y):
    """取 (x, y) 的 RGB 三元组。"""
    row = rows[y]
    i = x * channels
    return row[i], row[i + 1], row[i + 2]


def count_opaque_near_white(rows, width, height, channels,
                            thresh=240, min_alpha=250):
    """统计「接近白色且不透明」的像素数。

    用途：图标里的白云必须还在 —— 抠图时如果按饱和度全局抠，
    白云会跟着背景一起被抠掉，图标就少了一块。
    """
    total = 0
    for y in range(height):
        row = rows[y]
        for x in range(width):
            i = x * channels
            r, g, b = row[i], row[i + 1], row[i + 2]
            if r >= thresh and g >= thresh and b >= thresh:
                a = row[i + 3] if channels == 4 else 255
                if a >= min_alpha:
                    total += 1
    return total
