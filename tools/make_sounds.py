# -*- coding: utf-8 -*-
"""
音效合成（开发期一次性运行，游戏运行时只读取生成的 wav）

不下载任何第三方音频素材，全部用 Python 标准库（wave / array / math / random）
现场合成，避免版权问题。生成 4 个音效：

    pick_ok.wav     正确选择（箭头飞出）：掌声（多个随机拍击爆发 + 群体噪声底噪）
    pick_bad.wav    错误选择（被挡住）：下行的低沉蜂鸣 + 噪声，带一点失真
    level_clear.wav 通关：上行琶音 + 高频闪光
    fireworks.wav   全部通关：烟花（引信咻声 → 低频爆响 → 噼啪余响）

用法：
    python tools/make_sounds.py
输出：
    assets/sounds/*.wav
"""
import array
import math
import os
import random
import sys
import wave

SR = 44100
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "assets", "sounds")


# ---------------------------------------------------------------- 基础工具
def lowpass(buf, a):
    """一阶低通：y[n] = (1-a)*y[n-1] + a*x[n]，a 越小越闷。"""
    y = 0.0
    out = []
    for x in buf:
        y = (1 - a) * y + a * x
        out.append(y)
    return out


def highpass(buf, a):
    """一阶高通（差分 + 平滑），用来去掉低频轰鸣让声音更“清脆”。"""
    out = []
    prev_x = prev_y = 0.0
    for x in buf:
        y = a * (prev_y + x - prev_x)
        out.append(y)
        prev_x, prev_y = x, y
    return out


def normalize(buf, peak=0.92):
    m = max(abs(v) for v in buf) or 1.0
    k = peak / m
    return [v * k for v in buf]


def fade_edges(buf, ms_in=4, ms_out=60):
    n_in = int(SR * ms_in / 1000)
    n_out = int(SR * ms_out / 1000)
    n = len(buf)
    for i in range(min(n_in, n)):
        buf[i] *= i / n_in
    for i in range(min(n_out, n)):
        buf[n - 1 - i] *= i / n_out
    return buf


def mix(buf, src, offset, gain=1.0):
    """把 src 按偏移叠加进 buf。"""
    n = len(buf)
    for i, v in enumerate(src):
        j = offset + i
        if 0 <= j < n:
            buf[j] += v * gain
    return buf


def write_wav(name, buf):
    buf = fade_edges(normalize(buf))
    data = array.array("h", [int(max(-1.0, min(1.0, v)) * 32767) for v in buf])
    path = os.path.join(OUT, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    dur = len(buf) / SR
    rms = math.sqrt(sum(v * v for v in buf) / len(buf))
    print("  %-16s %5.2f 秒  峰值 %.2f  RMS %.3f" % (name, dur, max(abs(v) for v in buf), rms))


# ---------------------------------------------------------------- 各音效
def make_pick_ok():
    """掌声：多次随机拍击爆发 + 群体噪声底，带轻微混响。"""
    dur = 1.15
    n = int(SR * dur)
    rnd = random.Random(20260919)
    buf = [0.0] * n

    # 一个个“巴掌”：短噪声爆发 + 快速衰减
    for _ in range(int(dur * 26)):
        t0 = rnd.uniform(0.0, dur * 0.9)
        length = int(SR * 0.03)
        start = int(t0 * SR)
        amp = rnd.uniform(0.3, 1.0)
        for i in range(length):
            env = math.exp(-i / (SR * 0.007))
            v = rnd.uniform(-1, 1) * env * amp
            j = start + i
            if j < n:
                buf[j] += v
            # 一点点早期反射，听起来像在房间里
            j2 = start + i + int(SR * 0.045)
            if j2 < n:
                buf[j2] += v * 0.28

    # 人群底噪（逐渐增强后衰减）
    for i in range(n):
        t = i / SR
        env = min(1.0, t / 0.05) * math.exp(-t * 1.2)
        buf[i] += rnd.uniform(-1, 1) * 0.16 * env

    buf = highpass(lowpass(buf, 0.55), 0.55)     # 中高频为主 -> 更像拍手
    return buf


def make_pick_bad():
    """错误：从 420Hz 下行到 110Hz 的方波（带颤音）+ 少量噪声，短促发闷。

    注意别用高通：高通会把下行的基频滤掉，听起来就不再“往下掉”了。
    这里只用一阶低通去掉刺耳的高频，保留下滑的音高。
    """
    dur = 0.45
    n = int(SR * dur)
    rnd = random.Random(5)
    buf = []
    phase = 0.0
    for i in range(n):
        t = i / SR
        k = t / dur
        f = 110.0 + 310.0 * (1 - k) ** 1.6              # 420Hz -> 110Hz
        f *= 1.0 + 0.015 * math.sin(2 * math.pi * 24 * t)   # 轻微颤音
        phase += 2 * math.pi * f / SR
        saw = 2 * (phase / (2 * math.pi) % 1.0) - 1.0
        sq = 1.0 if math.sin(phase) >= 0 else -1.0
        tone = 0.5 * sq + 0.5 * saw
        env = min(1.0, t / 0.003) * math.exp(-t * 6.0)
        buf.append((tone * 0.9 + rnd.uniform(-1, 1) * 0.10) * env)
    return lowpass(buf, 0.8)


def make_level_clear():
    """通关：C5-E5-G5-C6 上行琶音，每个音带柔和的三角波音色与高频闪光。"""
    notes = [523.25, 659.25, 783.99, 1046.50]
    dur = 1.0
    n = int(SR * dur)
    buf = [0.0] * n
    rnd = random.Random(99)
    for k, f in enumerate(notes):
        start = int(SR * 0.11 * k)
        length = int(SR * 0.55)
        seg = []
        for i in range(length):
            t = i / SR
            env = min(1.0, t / 0.01) * math.exp(-t * 3.2)
            # 三角波 + 二次谐波，音色比正弦更亮
            tri = 2 / math.pi * math.asin(math.sin(2 * math.pi * f * t))
            seg.append((tri + 0.25 * math.sin(4 * math.pi * f * t)) * env * 0.5)
        mix(buf, seg, start)
    # 收尾的高频闪光
    for i in range(int(SR * 0.25)):
        t = i / SR
        j = int(SR * 0.42) + i
        if j < n:
            buf[j] += rnd.uniform(-1, 1) * 0.25 * math.exp(-t * 9)
    return buf


def make_fireworks():
    """烟花：引信咻声 → 低频爆响 + 噼啪余响（两次爆炸）。"""
    dur = 2.2
    n = int(SR * dur)
    rnd = random.Random(2026)
    buf = [0.0] * n

    def explosion(t0, size=1.0):
        # 咻——引信：0.3 秒的上行正弦
        whistle_len = int(SR * 0.3)
        seg = []
        ph = 0.0
        for i in range(whistle_len):
            t = i / SR
            f = 380 + 1500 * (t / 0.3)
            ph += 2 * math.pi * f / SR
            seg.append(math.sin(ph) * 0.35 * math.exp(-t * 2.0))
        mix(buf, seg, int(t0 * SR) - whistle_len)
        # 砰——低频爆响
        boom_len = int(SR * 0.5)
        seg = []
        ph = 0.0
        for i in range(boom_len):
            t = i / SR
            f = 90 * math.exp(-t * 6) + 42
            ph += 2 * math.pi * f / SR
            env = math.exp(-t * 6.5)
            noise = rnd.uniform(-1, 1) * math.exp(-t * 22) * 0.6
            seg.append((math.sin(ph) * 0.9 + noise) * env * size)
        mix(buf, seg, int(t0 * SR))
        # 噼啪余响：随机的细小炸裂
        for _ in range(int(90 * size)):
            tt = t0 + rnd.uniform(0.03, 0.75)
            length = int(SR * 0.006)
            amp = rnd.uniform(0.1, 0.5) * size
            for i in range(length):
                j = int(tt * SR) + i
                if j < n:
                    buf[j] += rnd.uniform(-1, 1) * amp * math.exp(-i / (SR * 0.002))

    explosion(0.34, size=1.0)
    explosion(1.05, size=0.62)
    return highpass(lowpass(buf, 0.9), 0.6)


def main():
    os.makedirs(OUT, exist_ok=True)
    print("合成音效 -> assets/sounds/")
    write_wav("pick_ok.wav", make_pick_ok())
    write_wav("pick_bad.wav", make_pick_bad())
    write_wav("level_clear.wav", make_level_clear())
    write_wav("fireworks.wav", make_fireworks())


if __name__ == "__main__":
    main()
