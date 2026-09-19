# -*- coding: utf-8 -*-
"""
AIGC 素材预处理（开发期一次性运行，游戏运行时不需要）

背景：AI 生成的箭头 / 爱心图是**纯白底、无透明通道**的（直接贴到棋盘上会
     带一个白方块），底板图右下角还带「AI生成」水印。本脚本把它们处理成
     可直接使用的素材：

1. 白底抠图（关键：只抠“与图片外框连通的白色区域”）
   - 如果简单地把所有近白像素设为透明，箭头内部的高光（也是白的）会被打穿成洞；
   - 所以用从四周边界出发的洪水填充（BFS），只把**与边界连通的背景**判为透明，
     内部高光自然保留；
   - 再把蒙版做一次高斯模糊，得到柔和的抗锯齿边缘（避免锯齿感）。
2. 自动裁剪到图形外框（getbbox），使图片中心 = 图形中心，方便按方向旋转。
3. 底板图裁掉右下角水印区域，并做降采样模糊，弱化它自带的细网格，
   作为界面背景使用（避免和棋盘的格子线冲突）。

用法：
    python tools/prepare_assets.py

输出：
    assets/arrow.png     箭头（默认朝左，游戏内按方向旋转）
    assets/heart.png     爱心（HUD 剩余失误）
    assets/board_bg.png  界面背景底纹
    assets/raw/          保留 AI 原始输出，便于溯源（游戏不读取）
"""
import collections
import os
import sys

from PIL import Image, ImageFilter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE, "assets")
RAW = os.path.join(ASSETS, "raw")

WHITE_MIN = 236          # 判定“近白背景”的阈值
FEATHER_RADIUS = 1.4     # 边缘羽化半径（像素）


def find_raw(keyword):
    """在 assets/ 与 assets/raw/ 里找名字含 keyword 的原始 AI 图。"""
    for d in (RAW, ASSETS):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if keyword in name and name.lower().endswith(".png"):
                return os.path.join(d, name)
    raise SystemExit("找不到原始图：%s" % keyword)


def cut_white_bg(img, white_min=WHITE_MIN):
    """从四周边界洪水填充，抠掉连通的白色背景，保留内部高光。"""
    img = img.convert("RGB")
    w, h = img.size
    px = img.load()

    def near_white(p):
        return p[0] >= white_min and p[1] >= white_min and p[2] >= white_min

    bg = bytearray(w * h)          # 1 = 背景
    queue = collections.deque()
    for x in range(w):             # 上下边界
        for y in (0, h - 1):
            if not bg[y * w + x] and near_white(px[x, y]):
                bg[y * w + x] = 1
                queue.append((x, y))
    for y in range(h):             # 左右边界
        for x in (0, w - 1):
            if not bg[y * w + x] and near_white(px[x, y]):
                bg[y * w + x] = 1
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                i = ny * w + nx
                if not bg[i] and near_white(px[nx, ny]):
                    bg[i] = 1
                    queue.append((nx, ny))

    # 蒙版：前景=255，背景=0；再模糊一次得到柔和边缘
    mask = Image.frombytes("L", (w, h), bytes(255 if not b else 0 for b in bg))
    mask = mask.filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def trim(img, pad=8):
    """裁剪到非透明外框（留一点边），使图形居中。"""
    bbox = img.getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    w, h = img.size
    return img.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(w, x1 + pad), min(h, y1 + pad)))


def main():
    os.makedirs(RAW, exist_ok=True)

    # ---- 箭头
    src = find_raw("arrow")
    arrow = trim(cut_white_bg(Image.open(src)))
    arrow.save(os.path.join(ASSETS, "arrow.png"))
    print("箭头：%s -> assets/arrow.png  输出尺寸 %s" % (os.path.basename(src), arrow.size))

    # ---- 爱心
    src = find_raw("heart")
    heart = trim(cut_white_bg(Image.open(src)))
    heart.save(os.path.join(ASSETS, "heart.png"))
    print("爱心：%s -> assets/heart.png  输出尺寸 %s" % (os.path.basename(src), heart.size))

    # ---- 背景底纹：裁掉右下角水印 + 降采样模糊（弱化自带网格）
    src = find_raw("board_pane")
    bg = Image.open(src).convert("RGB")
    w, h = bg.size
    bg = bg.crop((0, 0, int(w * 0.84), int(h * 0.91)))      # 切掉右下角水印
    small = bg.resize((96, 96), Image.LANCZOS)             # 先缩小
    bg = small.resize((720, 720), Image.BICUBIC)           # 再放大 = 柔化细网格
    bg.save(os.path.join(ASSETS, "board_bg.png"))
    print("底纹：%s -> assets/board_bg.png  输出尺寸 %s" % (os.path.basename(src), bg.size))

    # ---- 原始图归档到 assets/raw/（游戏不读取，仅供溯源）
    for name in os.listdir(ASSETS):
        if name.endswith(".png") and name not in ("arrow.png", "heart.png", "board_bg.png"):
            os.replace(os.path.join(ASSETS, name), os.path.join(RAW, name))
    print("原始 AI 输出已归档到 assets/raw/")


if __name__ == "__main__":
    main()
