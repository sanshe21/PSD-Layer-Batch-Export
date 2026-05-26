# -*- coding: utf-8 -*-
"""
封面自动生成 v2.0
====================
基于 PSD 模板批量生成封面
- 自动检测 clipping mask，使用 clip base 的 alpha 作为蒙版
- 底部缩略图条（中文字体、←→键导航、水平滚动条、滚轮滚动）
- 右侧大图支持鼠标拖拽、边框缩放、滚轮缩放
- 拖拽/缩放时显示分辨率实时预览（~60fps）
- 每张照片参数独立保存，批量导出
- 自动记忆上次 PSD/照片/输出路径
- 输出默认为照片文件夹下的"封面"子目录

核心渲染：显示分辨率快速预览 + PSD 分辨率精确导出
"""

import os
import sys
import json
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFont
from psd_tools import PSDImage

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}


def natural_sort_key(s):
    """自然排序 key：让 '2' 排在 '10' 前面。"""
    import re
    parts = re.split(r'(\d+)', s)
    result = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p), ''))
        else:
            result.append((1, 0, p.lower()))
    return result


# ═══════════════════ 配置文件 ═══════════════════

def get_config_path():
    """获取配置文件路径（放到用户数据目录，避免污染便携版目录）。"""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.join(os.environ.get("APPDATA", ""), "封面自动生成v2.0")
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, ".psd_cover_config.json")


def load_config():
    try:
        p = get_config_path()
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(data):
    try:
        p = get_config_path()
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ═══════════════════ 中文字体 ═══════════════════

def find_chinese_font(size=12):
    """查找系统中可用的中文字体。"""
    candidates = [
        "msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc",
        "simfang.ttf", "STKAITI.TTF", "STZHONGS.TTF",
    ]
    font_dirs = [
        r"C:\Windows\Fonts",
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    ]
    for d in font_dirs:
        for fn in candidates:
            fp = os.path.join(d, fn)
            if os.path.isfile(fp):
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ═══════════════════ PSD 工具函数 ═══════════════════

def collect_leaf_layers(psd):
    leaves = []
    def walk(group):
        for layer in group:
            if layer.is_group():
                walk(layer)
            else:
                leaves.append(layer)
    walk(psd)
    leaves.reverse()
    return leaves


def find_image_layers(psd):
    result = []
    for layer in reversed(collect_leaf_layers(psd)):
        try:
            x1, y1, x2, y2 = layer.bbox
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                continue
            is_so = hasattr(layer, 'smart_object') or getattr(layer, 'kind', '') == 'smartobject'
            if is_so:
                img = layer.topil()
            else:
                img = layer.composite()
            if img and img.size[0] > 0 and img.size[1] > 0:
                result.append(layer)
        except Exception:
            pass
    return result


def is_clipping_layer(layer):
    try:
        return bool(getattr(layer._record, 'clipping', 0) == 1)
    except Exception:
        return False


def find_clip_base(target, all_leaves):
    for layer in all_leaves:
        try:
            clips = getattr(layer, 'clip_layers', None)
            if clips and target in clips:
                return layer
        except Exception:
            pass
    return None


def select_best_layer(layers):
    if not layers:
        return None
    non_clip = [l for l in layers if not is_clipping_layer(l)]
    if non_clip:
        return max(non_clip, key=lambda l: (l.bbox[2]-l.bbox[0]) * (l.bbox[3]-l.bbox[1]))
    return max(layers, key=lambda l: (l.bbox[2]-l.bbox[0]) * (l.bbox[3]-l.bbox[1]))


def extract_layer_image(layer, psd_w, psd_h):
    try:
        x1, y1, x2, y2 = layer.bbox
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            return None
        is_so = hasattr(layer, 'smart_object') or getattr(layer, 'kind', '') == 'smartobject'
        if is_so:
            layer_img = layer.topil()
        else:
            layer_img = layer.composite()
        if layer_img is None:
            return None
        if layer_img.mode != 'RGBA':
            layer_img = layer_img.convert('RGBA')
        canvas = Image.new('RGBA', (psd_w, psd_h), (0, 0, 0, 0))
        if is_so:
            canvas.paste(layer_img, (x1, y1))
        else:
            canvas.paste(layer_img, (x1, y1), layer_img)
        return canvas
    except Exception:
        return None


class PSDRenderer:
    """PSD 合成渲染器 — PSD 分辨率精确渲染（用于导出和缩略图）。"""

    def __init__(self, psd, target_layer, all_leaves):
        self.psd = psd
        self.target = target_layer
        self.all_leaves = all_leaves
        self.tx1, self.ty1, self.tx2, self.ty2 = target_layer.bbox
        self.tw = self.tx2 - self.tx1
        self.th = self.ty2 - self.ty1

        self.clip_base = find_clip_base(target_layer, all_leaves)
        self.has_clip = self.clip_base is not None
        self._build_base()

    def _build_base(self):
        base_rgba = self.psd.composite().convert('RGBA')
        self.arr_base = np.array(base_rgba)
        self.base_shape = self.arr_base.shape
        h, w = self.base_shape[0], self.base_shape[1]

        if self.has_clip:
            self.clip_mask_arr = np.zeros((h, w), dtype=np.uint8)
            bx1, by1, bx2, by2 = self.clip_base.bbox
            mx1, my1 = max(bx1, 0), max(by1, 0)
            mx2, my2 = min(bx2, w), min(by2, h)
            if mx2 > mx1 and my2 > my1:
                base_topil = self.clip_base.topil()
                if base_topil.mode != 'RGBA':
                    base_topil = base_topil.convert('RGBA')
                base_alpha = base_topil.split()[3]
                src_x = mx1 - bx1
                src_y = my1 - by1
                mask_region = np.array(base_alpha.crop(
                    (src_x, src_y, src_x + mx2 - mx1, src_y + my2 - my1)))
                self.clip_mask_arr[my1:my2, mx1:mx2] = mask_region
        else:
            self.clip_mask_arr = np.full((h, w), 255, dtype=np.uint8)

    def render(self, new_image, offset_x=0, offset_y=0, scale=1.0):
        """全分辨率渲染（导出、缩略图用）。"""
        scaled_w = max(1, int(self.tw * scale))
        scaled_h = max(1, int(self.th * scale))

        img_ratio = new_image.width / new_image.height
        tgt_ratio = scaled_w / scaled_h

        if img_ratio > tgt_ratio:
            rh = scaled_h
            rw = int(scaled_h * img_ratio)
        else:
            rw = scaled_w
            rh = int(scaled_w / img_ratio)

        rw = max(rw, 1)
        rh = max(rh, 1)
        resized = new_image.resize((rw, rh), Image.LANCZOS)
        cl = (rw - scaled_w) // 2
        ct = (rh - scaled_h) // 2
        cropped = resized.crop((cl, ct, cl + scaled_w, ct + scaled_h))
        if cropped.mode != 'RGBA':
            cropped = cropped.convert('RGBA')

        h, w = self.base_shape[0], self.base_shape[1]
        new_arr = np.zeros((h, w, 4), dtype=np.uint8)

        paste_x = self.tx1 + offset_x
        paste_y = self.ty1 + offset_y

        px1 = max(paste_x, 0)
        py1 = max(paste_y, 0)
        px2 = min(paste_x + cropped.width, w)
        py2 = min(paste_y + cropped.height, h)

        if px2 > px1 and py2 > py1:
            nl = px1 - paste_x
            nt = py1 - paste_y
            nr = nl + (px2 - px1)
            nb = nt + (py2 - py1)
            region = np.array(cropped)[nt:nb, nl:nr]
            if region.shape[2] == 3:
                alpha_region = np.full(
                    (region.shape[0], region.shape[1], 1), 255, dtype=np.uint8)
                region = np.concatenate([region, alpha_region], axis=2)
            new_arr[py1:py2, px1:px2] = region

        new_arr[:, :, 3] = (
            new_arr[:, :, 3].astype(np.uint16)
            * self.clip_mask_arr.astype(np.uint16)
            // 255
        ).astype(np.uint8)

        alpha_f = new_arr[:, :, 3].astype(np.float32) / 255.0
        alpha_f3 = alpha_f[:, :, np.newaxis]
        result = (self.arr_base[:, :, :3].astype(np.float32) * (1 - alpha_f3)
                  + new_arr[:, :, :3].astype(np.float32) * alpha_f3)
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ═══════════════════ 辅助函数 ═══════════════════

def fit_image(img, max_w, max_h):
    if img is None:
        return None
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return None
    ratio = min(max_w / iw, max_h / ih, 1.0)
    if ratio < 1:
        return img.resize((int(iw * ratio), int(ih * ratio)), Image.LANCZOS)
    return img


def make_checker(w, h, size=8):
    checker = Image.new('RGB', (w, h), (220, 220, 220))
    px = checker.load()
    for y in range(h):
        for x in range(w):
            if (x // size + y // size) % 2 == 1:
                px[x, y] = (180, 180, 180)
    return checker


# ═══════════════════ 照片配置 ═══════════════════

class PhotoConfig:
    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0
        self._pil_image = None
        self._frame = None
        self._container = None
        self._thumb_canvas = None
        self._thumb_img = None

    def get_image(self):
        if self._pil_image is None:
            img = Image.open(self.path)
            if img.mode in ('CMYK', 'P'):
                img = img.convert('RGB')
            elif img.mode != 'RGBA':
                img = img.convert('RGBA')
            self._pil_image = img
        return self._pil_image


# ═══════════════════ 主应用 ═══════════════════

class PSDBatchCoverApp:
    BG = "#2b2b2b"
    PANEL = "#333333"
    CARD = "#3c3c3c"
    ACCENT = "#4a9eff"
    ACCENT_D = "#2d7ae0"
    TXT = "#e0e0e0"
    DIM = "#888888"
    RED = "#ff5555"
    GREEN = "#55ff88"
    BDR = "#555555"

    STRIP_H = 198
    THUMB_H = 178
    EDGE_THRESHOLD = 8

    def __init__(self, root):
        self.root = root
        self.root.title("封面自动生成 v2.0")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=self.BG)
        self._set_icon()

        self.cn_font = find_chinese_font(10)

        # 路径变量
        self.psd_path = tk.StringVar()
        self.photos_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        # PSD 状态
        self.psd_obj = None
        self.layers = []
        self.all_leaves = []
        self.selected_layer = None
        self.selected_idx = -1
        self.renderer = None

        # 照片
        self.photos = []
        self.active_photo_idx = -1
        self.is_processing = False
        self.is_generating_thumbs = False
        self._thumb_gen_id = 0  # 缩略图生成版本号，防止竞态

        # GUI 引用
        self.preview_photo = None
        self.layer_photo = None
        self.thumb_photos = []

        # 鼠标拖拽
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_orig_ox = 0
        self.drag_orig_oy = 0

        # 边框缩放
        self.resize_mode = None

        # ── 显示分辨率快速预览 ──
        self._fp_base = None       # numpy (dh, dw, 3) 显示分辨率基底
        self._fp_mask = None       # numpy (dh, dw) 显示分辨率蒙版
        self._fp_rep_disp = None   # numpy (rh, rw, 4) 显示分辨率替换图
        self._fp_ratio = 1.0       # PSD → 显示 缩放比
        self._fp_w = 0
        self._fp_h = 0
        self._fp_x = 0
        self._fp_y = 0
        self._fp_last_scale = None
        self._fp_canvas_id = None  # canvas image item
        self._fp_box_id = None     # canvas red box item
        self._resize_after_id = None

        # 显示比例（兼容旧代码）
        self.preview_scale = 1.0
        self.preview_img_x = 0
        self.preview_img_y = 0

        self._build_ui()
        self._bind_events()

        # 启动时加载上次的配置
        self.root.after(100, self._restore_config)

    def _set_icon(self):
        """设置窗口图标 — 兼容脚本和 PyInstaller 单文件模式。"""
        try:
            if getattr(sys, 'frozen', False):
                # PyInstaller 单文件模式：ico 在 _MEIPASS 临时目录
                base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base, 'app_icon.ico')
            if os.path.isfile(icon_path):
                img = Image.open(icon_path)
                self.icon_img = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self.icon_img)
        except Exception:
            pass

    # ─────────── UI 构建 ───────────

    def _build_ui(self):
        top = tk.Frame(self.root, bg=self.BG)
        top.pack(fill=tk.X, padx=20, pady=(12, 0))
        tk.Label(top, text="封面自动生成", bg=self.BG, fg=self.TXT,
                 font=("Microsoft YaHei UI", 18, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text="  v2.0  |  选择模板 → 选图层 → 调整 → 导出",
                 bg=self.BG, fg=self.DIM,
                 font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT, padx=(8, 0))

        # 右上角按钮（从左到右：关于此软件 → 打开输出文件夹 → 批量导出 PNG）
        self.export_btn = tk.Button(top, text="  批量导出 PNG  ",
                                    bg=self.GREEN, fg="#000",
                                    activebackground="#44dd66",
                                    font=("Microsoft YaHei UI", 10, "bold"),
                                    relief=tk.FLAT, padx=12, pady=3,
                                    cursor="hand2",
                                    command=self._start_export,
                                    state=tk.DISABLED)
        self.export_btn.pack(side=tk.RIGHT)

        self.open_btn = tk.Button(top, text="打开输出文件夹",
                                  bg=self.CARD, fg=self.TXT,
                                  activebackground=self.BDR,
                                  font=("Microsoft YaHei UI", 9),
                                  relief=tk.FLAT, padx=8, pady=3,
                                  cursor="hand2",
                                  command=self._open_output,
                                  state=tk.DISABLED)
        self.open_btn.pack(side=tk.RIGHT, padx=(0, 8))

        about_btn = tk.Button(top, text="关于此软件",
                              bg=self.CARD, fg=self.TXT,
                              activebackground=self.BDR,
                              font=("Microsoft YaHei UI", 9),
                              relief=tk.FLAT, padx=8, pady=3,
                              cursor="hand2",
                              command=self._show_about)
        about_btn.pack(side=tk.RIGHT, padx=(0, 8))

        paths = tk.Frame(self.root, bg=self.BG)
        paths.pack(fill=tk.X, padx=20, pady=(8, 0))
        self._path_row(paths, "PSD 模板", self.psd_path, self._browse_psd, "#ff9500")
        self._path_row(paths, "照片文件夹", self.photos_dir, self._browse_photos, "#34c759")
        self._path_row(paths, "输出文件夹", self.output_dir, self._browse_output, "#5ac8fa")

        mid = tk.Frame(self.root, bg=self.BG)
        mid.pack(fill=tk.BOTH, expand=True, padx=20, pady=(8, 0))

        # 左右面板用 PanedWindow，支持鼠标拖拽分隔条
        self.paned = tk.PanedWindow(mid, orient=tk.HORIZONTAL,
                                    bg=self.BG, sashwidth=5,
                                    sashrelief=tk.RAISED, bd=0,
                                    opaqueresize=True)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # 左面板
        left = tk.Frame(self.paned, bg=self.PANEL, width=280)
        self.paned.add(left, minsize=200, width=280)
        left.pack_propagate(False)

        tk.Label(left, text="图层选择", bg=self.PANEL, fg=self.TXT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(pady=(10, 2))
        tk.Label(left, text="点击查看图层内容", bg=self.PANEL, fg=self.DIM,
                 font=("Microsoft YaHei UI", 8)).pack()

        lf = tk.Frame(left, bg=self.CARD)
        lf.pack(fill=tk.X, padx=6, pady=6)
        self.layer_listbox = tk.Listbox(
            lf, height=5, bg=self.CARD, fg=self.TXT,
            selectbackground=self.ACCENT_D, selectforeground="#fff",
            font=("Consolas", 9), selectmode=tk.SINGLE,
            activestyle="none", highlightthickness=0, bd=0)
        self.layer_listbox.pack(fill=tk.X, padx=3, pady=3)
        self.layer_listbox.bind("<<ListboxSelect>>", self._on_layer_select)

        tk.Label(left, text="图层预览", bg=self.PANEL, fg=self.DIM,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(pady=(6, 2))
        self.layer_canvas = tk.Canvas(left, bg=self.CARD,
                                      highlightthickness=0, height=140)
        self.layer_canvas.pack(fill=tk.X, padx=6)
        self.layer_info = tk.Label(left, text="", bg=self.PANEL,
                                   fg=self.ACCENT,
                                   font=("Microsoft YaHei UI", 8),
                                   wraplength=250, justify=tk.LEFT)
        self.layer_info.pack(pady=(2, 6))

        sep = tk.Frame(left, bg=self.BDR, height=1)
        sep.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(left, text="当前照片调整", bg=self.PANEL, fg=self.TXT,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(pady=(4, 2))
        self.param_label = tk.Label(left, text="未选择照片", bg=self.PANEL,
                                    fg=self.DIM,
                                    font=("Consolas", 9),
                                    wraplength=250, justify=tk.LEFT)
        self.param_label.pack(pady=(0, 4))

        self.reset_btn = tk.Button(left, text="重置当前照片", bg=self.CARD,
                                   fg=self.TXT, activebackground=self.BDR,
                                   font=("Microsoft YaHei UI", 9),
                                   relief=tk.FLAT, padx=8, pady=3,
                                   cursor="hand2",
                                   command=self._reset_current_photo,
                                   state=tk.DISABLED)
        self.reset_btn.pack(pady=(0, 6))

        # 右面板
        right = tk.Frame(self.paned, bg=self.PANEL)
        self.paned.add(right, minsize=400)

        hdr = tk.Frame(right, bg=self.PANEL)
        hdr.pack(fill=tk.X, padx=8, pady=(8, 2))
        tk.Label(hdr, text="替换效果预览", bg=self.PANEL, fg=self.TXT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side=tk.LEFT)
        self.hint_label = tk.Label(hdr,
                                   text="拖拽移动 | 边框缩放 | 滚轮缩放 | ←→键切换",
                                   bg=self.PANEL, fg=self.DIM,
                                   font=("Microsoft YaHei UI", 8))
        self.hint_label.pack(side=tk.LEFT, padx=(12, 0))

        self.preview_canvas = tk.Canvas(right, bg="#1a1a1a",
                                        highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 8))

        # ═══ 底部：缩略图条 ═══
        strip_frame = tk.Frame(self.root, bg=self.PANEL)
        strip_frame.pack(fill=tk.X, padx=20, pady=(8, 0))

        strip_hdr = tk.Frame(strip_frame, bg=self.PANEL)
        strip_hdr.pack(fill=tk.X, padx=8, pady=(6, 2))
        tk.Label(strip_hdr, text="照片列表 (点击选择, ←→/滚轮滚动)",
                 bg=self.PANEL, fg=self.TXT,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
        self.strip_count = tk.Label(strip_hdr, text="", bg=self.PANEL,
                                    fg=self.DIM,
                                    font=("Microsoft YaHei UI", 8))
        self.strip_count.pack(side=tk.RIGHT)

        # 缩略图画布 + 明显的滚动条
        strip_canvas_frame = tk.Frame(strip_frame, bg=self.BDR, bd=2, relief=tk.SUNKEN)
        strip_canvas_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        self.strip_canvas = tk.Canvas(strip_canvas_frame, bg=self.CARD,
                                      highlightthickness=0, height=self.STRIP_H)
        h_scroll = tk.Scrollbar(strip_canvas_frame, orient=tk.HORIZONTAL,
                                command=self.strip_canvas.xview,
                                bg=self.BDR, troughcolor=self.CARD,
                                activebackground=self.ACCENT,
                                width=22)
        self.strip_canvas.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.strip_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.strip_inner = tk.Frame(self.strip_canvas, bg=self.CARD)
        self.strip_canvas.create_window((0, 0), window=self.strip_inner,
                                        anchor=tk.NW, tags="inner")
        self.strip_inner.bind("<Configure>",
            lambda e: self.strip_canvas.configure(
                scrollregion=self.strip_canvas.bbox("all")))

        self.strip_frame = strip_frame

        # 点击底部区域激活滚轮控制缩略图
        self._wheel_target = "preview"  # "preview" | "strip"
        self.strip_canvas.bind("<ButtonPress-1>", self._on_strip_click)
        self.strip_inner.bind("<ButtonPress-1>", self._on_strip_click)

        # ═══ 最底部 ═══
        bot = tk.Frame(self.root, bg=self.PANEL)
        bot.pack(fill=tk.X, padx=20, pady=(0, 12))

        self.progress_widget = tk.Canvas(bot, height=8, bg=self.CARD,
                                         highlightthickness=0)
        self.progress_widget.pack(fill=tk.X, padx=12, pady=(8, 2))

        status_frame = tk.Frame(bot, bg=self.PANEL)
        status_frame.pack(fill=tk.X, padx=12, pady=(2, 4))

        self.status_label = tk.Label(status_frame, text="就绪 — 正在加载配置...",
                                     bg=self.PANEL, fg=self.DIM,
                                     font=("Microsoft YaHei UI", 9))
        self.status_label.pack(side=tk.LEFT)

    def _on_strip_click(self, event):
        """点击底部区域时，切换滚轮控制为缩略图滚动。"""
        self._wheel_target = "strip"

    # ─── 全局滚轮路由 ───

    def _route_wheel(self, event):
        """全局滚轮：根据焦点路由到底部滚动或预览缩放。"""
        if self._wheel_target == "strip":
            self.strip_canvas.xview_scroll(
                int(-1 * (event.delta / 120)), "units")
        else:
            self._on_mouse_wheel(event)

    def _path_row(self, parent, label, var, cmd, color):
        f = tk.Frame(parent, bg=self.BG)
        f.pack(fill=tk.X, pady=2)
        c = tk.Canvas(f, width=8, height=8, bg=self.BG, highlightthickness=0)
        c.pack(side=tk.LEFT, padx=(0, 6), pady=5)
        c.create_oval(1, 1, 7, 7, fill=color, outline="")
        tk.Label(f, text=label, bg=self.BG, fg=self.TXT,
                 font=("Microsoft YaHei UI", 10), width=8,
                 anchor=tk.E).pack(side=tk.LEFT, padx=(0, 6))
        e = tk.Entry(f, textvariable=var, font=("Consolas", 10),
                     bg=self.CARD, fg=self.TXT, insertbackground=self.TXT,
                     relief=tk.FLAT, bd=0)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        e.bind("<Return>", lambda ev: cmd())
        tk.Button(f, text="浏览...", bg=self.CARD, fg=self.TXT,
                  activebackground=self.BDR,
                  font=("Microsoft YaHei UI", 9), relief=tk.FLAT,
                  padx=10, pady=2, cursor="hand2",
                  command=cmd).pack(side=tk.RIGHT, padx=(8, 0))

    # ─────────── 事件绑定 ───────────

    def _bind_events(self):
        self.preview_canvas.bind("<Configure>", self._on_preview_resize)
        self.preview_canvas.bind("<ButtonPress-1>", self._on_preview_click)
        self.preview_canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.preview_canvas.bind("<Motion>", self._on_mouse_move)

        # 全局滚轮路由（统一入口）
        self.root.bind("<MouseWheel>", self._route_wheel)

        # 全局键盘（←→ 滚动缩略图）
        self.root.bind("<Left>", self._on_key_left)
        self.root.bind("<Right>", self._on_key_right)

    # ─────────── 配置记忆 ───────────

    def _restore_config(self):
        """启动时恢复上次配置。"""
        cfg = load_config()
        psd_loaded = False
        photos_loaded = False

        if cfg.get('psd_path') and os.path.isfile(cfg['psd_path']):
            self.psd_path.set(cfg['psd_path'])
            try:
                self._load_psd(cfg['psd_path'])
                psd_loaded = True
            except Exception:
                pass

        if cfg.get('photos_dir') and os.path.isdir(cfg['photos_dir']):
            self.photos_dir.set(cfg['photos_dir'])
            if psd_loaded:
                try:
                    self._load_photos()
                    photos_loaded = True
                except Exception:
                    pass

        if cfg.get('output_dir') and os.path.isdir(cfg['output_dir']):
            self.output_dir.set(cfg['output_dir'])

        if psd_loaded:
            self.status_label.config(text="已恢复上次配置")
        else:
            self.status_label.config(text="就绪 — 请选择 PSD 模板")
        self._check_ready()

    def _save_current_config(self):
        cfg = {}
        if self.psd_path.get():
            cfg['psd_path'] = self.psd_path.get()
        if self.photos_dir.get():
            cfg['photos_dir'] = self.photos_dir.get()
        if self.output_dir.get():
            cfg['output_dir'] = self.output_dir.get()
        save_config(cfg)

    # ─────────── 文件浏览 ───────────

    def _browse_psd(self):
        path = filedialog.askopenfilename(
            title="选择 PSD 模板",
            filetypes=[("PSD 文件", "*.psd"), ("所有文件", "*.*")])
        if path:
            self.psd_path.set(path)
            self._load_psd(path)
            self._save_current_config()

    def _browse_photos(self):
        path = filedialog.askdirectory(title="选择照片文件夹")
        if path:
            self.photos_dir.set(path)
            self._load_photos()
            self._save_current_config()

    def _browse_output(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.output_dir.set(path)
            self._save_current_config()
            self._check_ready()

    # ─────────── PSD 加载 ───────────

    def _load_psd(self, path):
        self.status_label.config(text="正在加载 PSD ...")
        self.root.update_idletasks()
        try:
            psd = PSDImage.open(path)
            self.psd_obj = psd
            self.all_leaves = collect_leaf_layers(psd)
            self.layers = find_image_layers(psd)
            self.renderer = None
            self._fp_base = None  # 清除快速预览缓存

            if not self.layers:
                messagebox.showwarning("提示", "未找到可替换的图片图层。")
                self.status_label.config(text="未找到图层")
                self.layer_listbox.delete(0, tk.END)
                return

            self.layer_listbox.delete(0, tk.END)
            for i, layer in enumerate(self.layers):
                x1, y1, x2, y2 = layer.bbox
                w, h = x2 - x1, y2 - y1
                lt = "SO" if hasattr(layer, 'smart_object') else "PX"
                nm = getattr(layer, 'name', f'L{i}')
                clip_tag = ""
                if is_clipping_layer(layer):
                    clip_tag = " [CLIP]"
                base = find_clip_base(layer, self.all_leaves)
                if base:
                    clip_tag += f" -> {getattr(base, 'name', '?')}"
                clips = getattr(layer, 'clip_layers', None)
                if clips:
                    clip_tag += " [BASE]"
                self.layer_listbox.insert(tk.END,
                    f"[{i+1}] {nm} {lt} {w}x{h}{clip_tag}")

            best = select_best_layer(self.layers)
            idx = self.layers.index(best) if best in self.layers else 0
            self.layer_listbox.selection_set(idx)
            self.selected_layer = self.layers[idx]
            self.selected_idx = idx
            self._create_renderer()

            self._show_layer_preview()
            if self.photos:
                self._build_thumbnail_strip()
            self._refresh_thumbnails()
            clip_info = ""
            if self.renderer and self.renderer.has_clip:
                clip_info = f" (裁剪蒙版: {getattr(self.renderer.clip_base, 'name', '?')})"
            self.status_label.config(
                text=f"已加载: {os.path.basename(path)} "
                     f"({psd.width}x{psd.height}, {len(self.layers)} 个图层{clip_info})")
            self._check_ready()
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
            self.status_label.config(text="加载失败")

    def _on_layer_select(self, event):
        sel = self.layer_listbox.curselection()
        if sel and sel[0] < len(self.layers):
            self.selected_layer = self.layers[sel[0]]
            self.selected_idx = sel[0]
            self._create_renderer()
            self._show_layer_preview()
            if self.photos:
                self._build_thumbnail_strip()
            self._refresh_thumbnails()
            if self.active_photo_idx >= 0:
                self._update_preview()

    def _create_renderer(self):
        if self.psd_obj and self.selected_layer:
            self.status_label.config(text="正在预计算合成基底 ...")
            self.root.update_idletasks()
            try:
                self.renderer = PSDRenderer(
                    self.psd_obj, self.selected_layer, self.all_leaves)
                self._fp_base = None
            except Exception as e:
                self.renderer = None
                self.status_label.config(text=f"渲染器创建失败: {e}")

    # ─────────── 图层预览 ───────────

    def _show_layer_preview(self):
        self.layer_canvas.delete("all")
        if not self.selected_layer:
            return
        self.root.update_idletasks()
        cw = max(self.layer_canvas.winfo_width(), 240)
        ch = max(self.layer_canvas.winfo_height(), 140)
        try:
            li = extract_layer_image(self.selected_layer,
                                     self.psd_obj.width, self.psd_obj.height)
            if li is None:
                self.layer_info.config(text="无预览")
                return
            fitted = fit_image(li, cw - 6, ch - 6)
            if fitted is None:
                return
            checker = make_checker(fitted.size[0], fitted.size[1])
            checker.paste(fitted, (0, 0), fitted)
            self.layer_photo = ImageTk.PhotoImage(checker)
            x = (cw - checker.size[0]) // 2
            y = (ch - checker.size[1]) // 2
            self.layer_canvas.create_image(x, y, anchor=tk.NW,
                                           image=self.layer_photo)
            nm = getattr(self.selected_layer, 'name', '?')
            x1, y1, x2, y2 = self.selected_layer.bbox
            self.layer_info.config(
                text=f"{nm}\n({x1},{y1})->({x2},{y2}) {x2-x1}x{y2-y1}")
        except Exception as e:
            self.layer_info.config(text=str(e))

    # ─────────── 照片加载 & 缩略图 ───────────

    def _load_photos(self):
        d = self.photos_dir.get()
        if not os.path.isdir(d):
            return
        self.photos = []
        for f in sorted(os.listdir(d), key=natural_sort_key):
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                self.photos.append(PhotoConfig(os.path.join(d, f)))

        if not self.photos:
            messagebox.showinfo("提示", "未找到图片文件。")
            return

        # 自动设置输出文件夹
        default_output = os.path.join(d, "封面")
        os.makedirs(default_output, exist_ok=True)
        self.output_dir.set(default_output)
        self._save_current_config()

        self.active_photo_idx = 0
        self._fp_base = None  # 清除缓存
        self._build_thumbnail_strip()
        self._generate_all_thumbnails()
        self._update_preview()
        self._check_ready()

    def _build_thumbnail_strip(self):
        for w in self.strip_inner.winfo_children():
            w.destroy()
        self.thumb_photos = []
        self._thumb_gen_id += 1  # 使正在运行的缩略图生成线程失效

        psd_ratio = 1.0
        if self.renderer:
            psd_ratio = self.renderer.psd.width / self.renderer.psd.height
        thumb_h = self.THUMB_H
        thumb_w = max(40, int(thumb_h * psd_ratio))

        for i, pc in enumerate(self.photos):
            frame = tk.Frame(self.strip_inner, bg=self.CARD)
            frame.pack(side=tk.LEFT, padx=3, pady=4)

            container = tk.Frame(frame, bg=self.BDR, bd=2, relief=tk.SOLID)
            container.pack()

            tc = tk.Canvas(container, width=thumb_w, height=thumb_h,
                           bg="#1a1a1a", highlightthickness=0)
            tc.pack()
            tc.bind("<Button-1>", lambda e, idx=i: self._select_photo(idx))

            pc._frame = frame
            pc._container = container
            pc._thumb_canvas = tc

        self.strip_count.config(text=f"共 {len(self.photos)} 张")
        self._highlight_active_thumb()

    def _highlight_active_thumb(self):
        for i, pc in enumerate(self.photos):
            if i == self.active_photo_idx:
                pc._container.configure(bg=self.ACCENT, bd=2)
            else:
                pc._container.configure(bg=self.BDR, bd=2)

    def _make_thumbnail(self, result, name):
        psd_ratio = 1.0
        if self.renderer:
            psd_ratio = self.renderer.psd.width / self.renderer.psd.height
        thumb_h = self.THUMB_H
        tw = max(40, int(thumb_h * psd_ratio))
        thumb = result.resize((tw, thumb_h), Image.LANCZOS)
        try:
            thumb_rgba = thumb.convert('RGBA')
            bar_h = 18
            bar = Image.new('RGBA', (tw, bar_h), (0, 0, 0, 170))
            thumb_rgba.paste(bar, (0, thumb_h - bar_h), bar)
            draw = ImageDraw.Draw(thumb_rgba)
            display_name = name if len(name) <= 50 else name[:48] + "…"
            draw.text((4, thumb_h - bar_h + 2), display_name,
                      fill=(255, 255, 255), font=self.cn_font)
            return thumb_rgba.convert('RGB'), tw
        except Exception:
            return thumb, tw

    def _generate_all_thumbnails(self):
        if not self.renderer or not self.photos:
            return
        self.is_generating_thumbs = True
        self._thumb_gen_id += 1  # 使旧线程失效
        self.status_label.config(text="正在生成缩略图预览 ...")
        t = threading.Thread(target=self._gen_thumbs_worker, daemon=True)
        t.start()

    def _gen_thumbs_worker(self):
        renderer = self.renderer
        if not renderer:
            return
        total = len(self.photos)
        gen_id = self._thumb_gen_id  # 记录当前版本

        for i, pc in enumerate(self.photos):
            # 检查是否已被新请求取代
            if gen_id != self._thumb_gen_id:
                return
            try:
                img = pc.get_image()
                result = renderer.render(img, pc.offset_x, pc.offset_y, pc.scale)
                thumb, tw = self._make_thumbnail(result, pc.name)
                pc._thumb_img = ImageTk.PhotoImage(thumb)
                self.thumb_photos.append(pc._thumb_img)

                self.root.after(0, lambda idx=i, c=i+1, t=total, gid=gen_id: (
                    self.photos[idx]._thumb_canvas.delete("all"),
                    self.photos[idx]._thumb_canvas.create_image(
                        0, 0, anchor=tk.NW,
                        image=self.photos[idx]._thumb_img),
                    self.status_label.config(
                        text=f"生成缩略图 {c}/{t} ...")
                    if gid == self._thumb_gen_id else None
                ))
            except Exception as e:
                print(f"[缩略图失败] {pc.name}: {e}")

        if gen_id != self._thumb_gen_id:
            return
        self.is_generating_thumbs = False
        self.root.after(0, lambda: (
            self._highlight_active_thumb(),
            self._update_preview(),
            self._check_ready(),
            self.status_label.config(text="就绪 — 点击缩略图查看效果，拖拽调整")
        ))

    def _update_single_thumbnail(self, idx):
        pc = self.photos[idx]
        if not self.renderer:
            return
        try:
            img = pc.get_image()
            result = self.renderer.render(img, pc.offset_x, pc.offset_y, pc.scale)
            thumb, tw = self._make_thumbnail(result, pc.name)
            pc._thumb_img = ImageTk.PhotoImage(thumb)
            if not hasattr(pc, '_thumb_ref'):
                pc._thumb_ref = []
            pc._thumb_ref.append(pc._thumb_img)
            self.root.after(0, lambda: (
                pc._thumb_canvas.delete("all"),
                pc._thumb_canvas.create_image(0, 0, anchor=tk.NW, image=pc._thumb_img)
            ))
        except Exception:
            pass

    def _select_photo(self, idx):
        if idx < 0 or idx >= len(self.photos):
            return
        self.active_photo_idx = idx
        self._wheel_target = "strip"  # 点击底部照片，滚轮控制缩略图
        self._fp_base = None  # 照片变了，清除快速预览缓存
        self._fp_rep_disp = None
        self._fp_last_scale = None
        self._highlight_active_thumb()
        self._update_preview()
        self.reset_btn.config(state=tk.NORMAL)
        self._scroll_thumb_into_view(idx)

    def _scroll_thumb_into_view(self, idx):
        if not self.photos or idx < 0 or idx >= len(self.photos):
            return
        pc = self.photos[idx]
        if not pc._frame:
            return
        self.root.update_idletasks()
        try:
            x = pc._frame.winfo_rootx() - self.strip_canvas.winfo_rootx()
            w = pc._frame.winfo_width()
            canvas_w = self.strip_canvas.winfo_width()
            if x < 0:
                self.strip_canvas.xview_scroll(int(x // 40) - 1, "units")
            elif x + w > canvas_w:
                overflow = x + w - canvas_w
                self.strip_canvas.xview_scroll(int(overflow // 40) + 1, "units")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # ═══  显示分辨率快速预览（拖拽实时渲染）═══
    # ═══════════════════════════════════════════════════

    def _init_fast_preview(self):
        """初始化显示分辨率缓存。将 PSD 基底和蒙版降到显示尺寸（~400×700），
        拖拽时只在这个小尺寸上做 alpha blend，每帧 ~15ms。"""
        if not self.renderer or self.active_photo_idx < 0:
            return
        self.root.update_idletasks()
        cw = max(self.preview_canvas.winfo_width(), 100)
        ch = max(self.preview_canvas.winfo_height(), 100)

        psd_w = self.renderer.psd.width
        psd_h = self.renderer.psd.height

        ratio = min((cw - 16) / psd_w, (ch - 16) / psd_h, 1.0)
        dw = max(1, int(psd_w * ratio))
        dh = max(1, int(psd_h * ratio))

        self._fp_ratio = ratio
        self._fp_w = dw
        self._fp_h = dh
        self._fp_x = (cw - dw) // 2
        self._fp_y = (ch - dh) // 2
        self.preview_scale = ratio
        self.preview_img_x = self._fp_x
        self.preview_img_y = self._fp_y

        # 基底 RGB → 显示分辨率
        base_rgb = Image.fromarray(self.renderer.arr_base[:, :, :3])
        self._fp_base = np.array(base_rgb.resize((dw, dh), Image.BILINEAR))

        # 蒙版 → 显示分辨率
        mask_img = Image.fromarray(self.renderer.clip_mask_arr)
        self._fp_mask = np.array(mask_img.resize((dw, dh), Image.BILINEAR))

        # 替换图缓存清除
        self._fp_rep_disp = None
        self._fp_last_scale = None

        # 设置 canvas（复用 item 或新建）
        self.preview_canvas.delete("all")
        self._fp_box_id = None
        self._fp_canvas_id = self.preview_canvas.create_image(
            self._fp_x, self._fp_y, anchor=tk.NW)

    def _recompute_fast_replacement(self):
        """预计算替换图在显示分辨率的版本（仅 scale 变化时重算）。"""
        if self.active_photo_idx < 0:
            return
        pc = self.photos[self.active_photo_idx]
        scale = pc.scale

        if scale == self._fp_last_scale and self._fp_rep_disp is not None:
            return
        self._fp_last_scale = scale

        tw, th = self.renderer.tw, self.renderer.th
        scaled_w = max(1, int(tw * scale))
        scaled_h = max(1, int(th * scale))

        img = pc.get_image()
        img_ratio = img.width / img.height
        tgt_ratio = scaled_w / scaled_h

        if img_ratio > tgt_ratio:
            rh = scaled_h
            rw = int(scaled_h * img_ratio)
        else:
            rw = scaled_w
            rh = int(scaled_w / img_ratio)

        rw = max(rw, 1)
        rh = max(rh, 1)
        resized = img.resize((rw, rh), Image.BILINEAR)  # BILINEAR 更快
        cl = (rw - scaled_w) // 2
        ct = (rh - scaled_h) // 2
        cropped = resized.crop((cl, ct, cl + scaled_w, ct + scaled_h))
        if cropped.mode != 'RGBA':
            cropped = cropped.convert('RGBA')

        # 降到显示分辨率
        disp_rw = max(1, int(cropped.width * self._fp_ratio))
        disp_rh = max(1, int(cropped.height * self._fp_ratio))
        self._fp_rep_disp = np.array(cropped.resize((disp_rw, disp_rh), Image.BILINEAR))

    def _fast_render_update(self):
        """显示分辨率实时渲染（拖拽/缩放时调用，~15ms/帧）。"""
        if self._fp_base is None:
            self._init_fast_preview()
        if self._fp_base is None:
            return

        pc = self.photos[self.active_photo_idx]
        self._recompute_fast_replacement()

        s = self._fp_ratio
        dw, dh = self._fp_w, self._fp_h

        # 替换图在显示画布上的位置
        paste_dx = int((self.renderer.tx1 + pc.offset_x) * s)
        paste_dy = int((self.renderer.ty1 + pc.offset_y) * s)
        rep_disp_h, rep_disp_w = self._fp_rep_disp.shape[0], self._fp_rep_disp.shape[1]

        # 复制基底
        result = self._fp_base.copy()

        # 计算粘贴区域
        px1 = max(paste_dx, 0)
        py1 = max(paste_dy, 0)
        px2 = min(paste_dx + rep_disp_w, dw)
        py2 = min(paste_dy + rep_disp_h, dh)

        if px2 > px1 and py2 > py1:
            nl = px1 - paste_dx
            nt = py1 - paste_dy
            nr = nl + (px2 - px1)
            nb = nt + (py2 - py1)
            rep_region = self._fp_rep_disp[nt:nb, nl:nr]

            # 取蒙版区域
            mask_region = self._fp_mask[py1:py2, px1:px2].astype(np.float32) / 255.0

            # 替换图 alpha × 蒙版
            rep_alpha = rep_region[:, :, 3].astype(np.float32) / 255.0
            combined_alpha = rep_alpha * mask_region

            # Alpha blend（只在替换区域内操作）
            alpha3 = combined_alpha[:, :, np.newaxis]
            result[py1:py2, px1:px2] = np.clip(
                result[py1:py2, px1:px2].astype(np.float32) * (1 - alpha3)
                + rep_region[:, :, :3].astype(np.float32) * alpha3,
                0, 255
            ).astype(np.uint8)

        # 转换为 PhotoImage
        result_pil = Image.fromarray(result)
        self._preview_photo = ImageTk.PhotoImage(result_pil)
        self.preview_canvas.itemconfig(self._fp_canvas_id, image=self._preview_photo)

        # 更新红框
        self._update_red_box()

        # 更新参数
        self.param_label.config(
            text=f"offset: ({pc.offset_x}, {pc.offset_y})\n"
                 f"scale: {pc.scale:.2f}\n"
                 f"photo: {pc.name}")

    def _update_red_box(self):
        """在 canvas 上绘制/更新红框。"""
        if self._fp_box_id is not None:
            try:
                self.preview_canvas.delete(self._fp_box_id)
            except Exception:
                pass
            self._fp_box_id = None

        if not self.renderer or self.active_photo_idx < 0:
            return

        pc = self.photos[self.active_photo_idx]
        s = self._fp_ratio
        bx1 = int((self.renderer.tx1 + pc.offset_x) * s) + self._fp_x
        by1 = int((self.renderer.ty1 + pc.offset_y) * s) + self._fp_y
        bw = int(self.renderer.tw * pc.scale * s)
        bh = int(self.renderer.th * pc.scale * s)

        self._fp_box_id = self.preview_canvas.create_rectangle(
            bx1, by1, bx1 + bw, by1 + bh,
            outline=self.RED, width=2)

    def _update_preview(self):
        """完整预览更新（照片/图层/窗口变化时调用）。"""
        if self.renderer is None or self.active_photo_idx < 0:
            self.preview_canvas.delete("all")
            self._fp_canvas_id = None
            self._fp_box_id = None
            self.preview_canvas.create_text(
                self.preview_canvas.winfo_width() // 2,
                self.preview_canvas.winfo_height() // 2,
                text="请选择 PSD 模板和照片文件夹",
                fill=self.DIM, font=("Microsoft YaHei UI", 12))
            return
        self._init_fast_preview()
        self._fast_render_update()

    def _on_preview_resize(self, event):
        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.root.after(80, self._do_resize)

    def _do_resize(self):
        self._resize_after_id = None
        self._fp_base = None
        if self.active_photo_idx >= 0 and self.renderer:
            self._update_preview()

    def _refresh_thumbnails(self):
        if self.photos and self.renderer:
            self._generate_all_thumbnails()

    # ─────────── 替换矩形坐标转换 ───────────

    def _get_rect_on_canvas(self):
        if not self.renderer or self.active_photo_idx < 0:
            return None
        pc = self.photos[self.active_photo_idx]
        s = self._fp_ratio if self._fp_ratio else self.preview_scale
        tx1, ty1 = self.renderer.tx1, self.renderer.ty1
        tw, th = self.renderer.tw, self.renderer.th
        paste_x = tx1 + pc.offset_x
        paste_y = ty1 + pc.offset_y
        box_w = tw * pc.scale
        box_h = th * pc.scale
        img_x = self._fp_x if self._fp_x else self.preview_img_x
        img_y = self._fp_y if self._fp_y else self.preview_img_y
        cx1 = img_x + paste_x * s
        cy1 = img_y + paste_y * s
        cx2 = img_x + (paste_x + box_w) * s
        cy2 = img_y + (paste_y + box_h) * s
        return cx1, cy1, cx2, cy2

    # ─── 鼠标交互 ───

    def _on_mouse_move(self, event):
        if self.active_photo_idx < 0 or not self.photos:
            return
        if self.dragging or self.resize_mode:
            return

        rect = self._get_rect_on_canvas()
        if not rect:
            self.preview_canvas.config(cursor="")
            return

        cx1, cy1, cx2, cy2 = rect
        e = self.EDGE_THRESHOLD
        ex = event.x
        ey = event.y

        near_r = abs(ex - cx2) < e and cy1 - e < ey < cy2 + e
        near_l = abs(ex - cx1) < e and cy1 - e < ey < cy2 + e
        near_b = abs(ey - cy2) < e and cx1 - e < ex < cx2 + e
        near_t = abs(ey - cy1) < e and cx1 - e < ex < cx2 + e

        if (near_r and near_b) or (near_l and near_t):
            self.preview_canvas.config(cursor="size_nw_se")
        elif (near_r and near_t) or (near_l and near_b):
            self.preview_canvas.config(cursor="size_ne_sw")
        elif near_r or near_l:
            self.preview_canvas.config(cursor="sb_h_double_arrow")
        elif near_b or near_t:
            self.preview_canvas.config(cursor="sb_v_double_arrow")
        elif cx1 <= ex <= cx2 and cy1 <= ey <= cy2:
            self.preview_canvas.config(cursor="fleur")
        else:
            self.preview_canvas.config(cursor="")

    def _on_preview_click(self, event):
        """点击预览区域：激活滚轮缩放模式，然后处理拖拽/缩放。"""
        self._wheel_target = "preview"
        self._on_mouse_down_impl(event)

    def _on_mouse_down_impl(self, event):
        if self.active_photo_idx < 0 or not self.photos:
            return
        pc = self.photos[self.active_photo_idx]

        rect = self._get_rect_on_canvas()
        if rect:
            cx1, cy1, cx2, cy2 = rect
            e = self.EDGE_THRESHOLD
            near_r = abs(event.x - cx2) < e and cy1 - e < event.y < cy2 + e
            near_l = abs(event.x - cx1) < e and cy1 - e < event.y < cy2 + e
            near_b = abs(event.y - cy2) < e and cx1 - e < event.x < cx2 + e
            near_t = abs(event.y - cy1) < e and cx1 - e < event.x < cx2 + e

            edges = set()
            if near_r: edges.add('right')
            if near_l: edges.add('left')
            if near_b: edges.add('bottom')
            if near_t: edges.add('top')

            if edges:
                self.resize_mode = {
                    'edges': edges,
                    'start_x': event.x,
                    'start_y': event.y,
                    'orig_left_psd': self.renderer.tx1 + pc.offset_x,
                    'orig_top_psd': self.renderer.ty1 + pc.offset_y,
                    'orig_right_psd': self.renderer.tx1 + pc.offset_x
                                     + self.renderer.tw * pc.scale,
                    'orig_bottom_psd': self.renderer.ty1 + pc.offset_y
                                      + self.renderer.th * pc.scale,
                }
                return

        self.dragging = True
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.drag_orig_ox = pc.offset_x
        self.drag_orig_oy = pc.offset_y

    def _on_mouse_drag(self, event):
        if self.active_photo_idx < 0:
            return
        pc = self.photos[self.active_photo_idx]

        if self.resize_mode:
            rm = self.resize_mode
            s = self.preview_scale
            edges = rm['edges']

            orig_l = rm['orig_left_psd']
            orig_t = rm['orig_top_psd']
            orig_r = rm['orig_right_psd']
            orig_b = rm['orig_bottom_psd']

            new_l, new_t, new_r, new_b = orig_l, orig_t, orig_r, orig_b

            if 'right' in edges:
                new_r = orig_r + (event.x - rm['start_x']) / s
            if 'left' in edges:
                new_l = orig_l + (event.x - rm['start_x']) / s
            if 'bottom' in edges:
                new_b = orig_b + (event.y - rm['start_y']) / s
            if 'top' in edges:
                new_t = orig_t + (event.y - rm['start_y']) / s

            new_w = new_r - new_l
            new_h = new_b - new_t

            if new_w < 20 or new_h < 20:
                return

            scale_w = new_w / self.renderer.tw
            scale_h = new_h / self.renderer.th

            has_h = 'right' in edges or 'left' in edges
            has_v = 'bottom' in edges or 'top' in edges
            if has_h and has_v:
                new_scale = (scale_w + scale_h) / 2
            elif has_h:
                new_scale = scale_w
            else:
                new_scale = scale_h

            new_scale = max(0.1, min(5.0, new_scale))

            if 'right' in edges and 'left' not in edges:
                new_offset_x = orig_l - self.renderer.tx1
            elif 'left' in edges and 'right' not in edges:
                new_offset_x = orig_r - self.renderer.tx1 - self.renderer.tw * new_scale
            else:
                new_offset_x = new_l - self.renderer.tx1

            if 'bottom' in edges and 'top' not in edges:
                new_offset_y = orig_t - self.renderer.ty1
            elif 'top' in edges and 'bottom' not in edges:
                new_offset_y = orig_b - self.renderer.ty1 - self.renderer.th * new_scale
            else:
                new_offset_y = new_t - self.renderer.ty1

            pc.scale = new_scale
            pc.offset_x = int(new_offset_x)
            pc.offset_y = int(new_offset_y)
            self._fast_render_update()
            return

        if not self.dragging:
            return
        dx = int((event.x - self.drag_start_x) / self.preview_scale)
        dy = int((event.y - self.drag_start_y) / self.preview_scale)
        pc.offset_x = self.drag_orig_ox + dx
        pc.offset_y = self.drag_orig_oy + dy
        self._fast_render_update()

    def _on_mouse_up(self, event):
        if self.resize_mode:
            self.resize_mode = None
            self._update_single_thumbnail(self.active_photo_idx)
            return
        if self.dragging:
            self.dragging = False
            self._update_single_thumbnail(self.active_photo_idx)

    # ─── 滚轮缩放 ───

    def _on_mouse_wheel(self, event):
        if self.active_photo_idx < 0 or not self.photos:
            return
        pc = self.photos[self.active_photo_idx]
        delta = event.delta / 120.0
        if event.state & 0x1:
            delta *= 0.2
        pc.scale = max(0.1, min(5.0, pc.scale + delta * 0.05))
        self._fast_render_update()

    def _on_mouse_wheel_linux(self, event, direction):
        if self.active_photo_idx < 0 or not self.photos:
            return
        pc = self.photos[self.active_photo_idx]
        step = 0.02 if (event.state & 0x1) else 0.05
        pc.scale = max(0.1, min(5.0, pc.scale + direction * step))
        self._fast_render_update()

    # ─── 键盘导航：←→ 只滚动底部缩略图 ───

    def _on_key_left(self, event):
        self.strip_canvas.xview_scroll(-1, "units")

    def _on_key_right(self, event):
        self.strip_canvas.xview_scroll(1, "units")

    def _reset_current_photo(self):
        if self.active_photo_idx < 0:
            return
        pc = self.photos[self.active_photo_idx]
        pc.offset_x = 0
        pc.offset_y = 0
        pc.scale = 1.0
        self._fp_rep_disp = None
        self._fp_last_scale = None
        self._update_preview()
        self._update_single_thumbnail(self.active_photo_idx)

    # ─────────── 批量导出 ───────────

    def _check_ready(self):
        ready = (self.renderer is not None
                 and len(self.photos) > 0
                 and self.output_dir.get()
                 and not self.is_generating_thumbs)
        self.export_btn.config(state=tk.NORMAL if ready else tk.DISABLED)

    def _start_export(self):
        if self.is_processing or not self.photos:
            return
        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showinfo("提示", "请选择输出文件夹。")
            return
        os.makedirs(output_dir, exist_ok=True)

        self.is_processing = True
        self.export_btn.config(state=tk.DISABLED, bg="#666666")
        t = threading.Thread(target=self._export_worker,
                             args=(output_dir,), daemon=True)
        t.start()

    def _export_worker(self, output_dir):
        renderer = self.renderer
        if not renderer:
            return
        total = len(self.photos)
        success = 0
        failed = 0

        self.root.after(0, lambda: self.status_label.config(
            text=f"导出 0/{total} ..."))

        for i, pc in enumerate(self.photos):
            out = os.path.join(output_dir, f"{pc.name}.png")
            try:
                img = pc.get_image()
                result = renderer.render(img, pc.offset_x, pc.offset_y, pc.scale)
                result.save(out, 'PNG')
                success += 1
            except Exception as e:
                failed += 1
                print(f"[失败] {pc.name}: {e}")

            c = i + 1
            pct = c / total * 100
            self.root.after(0, lambda p=pct, cc=c, t=total: (
                self._update_progress_bar(p),
                self.status_label.config(
                    text=f"导出 {cc}/{t} ({p:.0f}%)")
            ))

        self.is_processing = False
        self.root.after(0, lambda: self._on_export_done(success, failed, output_dir))

    def _update_progress_bar(self, pct):
        w = self.progress_widget.winfo_width()
        self.progress_widget.delete("all")
        fill_w = int(w * pct / 100)
        if fill_w > 0:
            self.progress_widget.create_rectangle(
                0, 0, fill_w, 8, fill=self.GREEN, outline="")
        self.progress_widget.create_rectangle(
            0, 0, w, 8, outline=self.BDR)

    def _on_export_done(self, success, failed, output_dir):
        self.export_btn.config(state=tk.NORMAL, bg=self.GREEN)
        self.open_btn.config(state=tk.NORMAL)
        self.status_label.config(
            text=f"导出完成! 成功 {success}, 失败 {failed}")
        if failed > 0:
            messagebox.showwarning("完成",
                f"成功: {success}, 失败: {failed}\n{output_dir}")
        else:
            messagebox.showinfo("完成",
                f"全部成功! {success} 个文件。\n{output_dir}")

    def _open_output(self):
        p = self.output_dir.get()
        if os.path.isdir(p):
            os.startfile(p)

    def _show_about(self):
        """显示关于我们弹窗。"""
        win = tk.Toplevel(self.root)
        win.title("关于此软件")
        win.geometry("360x260")
        win.resizable(False, False)
        win.configure(bg=self.BG)
        win.transient(self.root)
        win.grab_set()

        # Center
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 360) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
        win.geometry(f"360x260+{x}+{y}")

        # Icon
        c = tk.Canvas(win, width=48, height=48, bg=self.BG, highlightthickness=0)
        c.pack(pady=(20, 12))
        c.create_oval(2, 2, 46, 46, fill="#141414", outline="")
        c.create_text(24, 25, text="fm", fill="white", font=("Arial", 16, "bold"))

        tk.Label(win, text="封面自动生成 v2.0", bg=self.BG, fg=self.TXT,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(0, 4))

        tk.Label(win, text="PSD 模板批量替换照片并导出封面", bg=self.BG, fg=self.DIM,
                 font=("Microsoft YaHei UI", 10)).pack(pady=(0, 16))

        info_items = [
            ("作者：", "SANSHE三社"),
            ("反馈邮箱：", "SANSHEX@163.com"),
            ("开源地址：", "https://github.com/sanshe21?tab=repositories"),
        ]
        for label, value in info_items:
            row = tk.Frame(win, bg=self.BG)
            row.pack(fill=tk.X, padx=40, pady=2)
            tk.Label(row, text=label, bg=self.BG, fg=self.DIM,
                     font=("Microsoft YaHei UI", 10), width=8, anchor="e").pack(side=tk.LEFT)
            val_lbl = tk.Label(row, text=value, bg=self.BG, fg=self.ACCENT,
                               font=("Microsoft YaHei UI", 10), cursor="hand2")
            val_lbl.pack(side=tk.LEFT)
            if value.startswith("http"):
                val_lbl.bind("<Button-1>", lambda e, url=value: webbrowser.open(url))

        tk.Button(win, text="关闭", command=win.destroy,
                  bg=self.CARD, fg=self.TXT, activebackground=self.BDR,
                  font=("Microsoft YaHei UI", 10), relief=tk.FLAT,
                  padx=20, pady=4, cursor="hand2").pack(pady=(16, 0))


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app = PSDBatchCoverApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
