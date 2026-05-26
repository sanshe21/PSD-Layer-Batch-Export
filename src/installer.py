#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面自动生成 v2.0 — 扁平化安装向导"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import struct
import io
import zipfile
import subprocess
import ctypes

APP_NAME = "封面自动生成 v2.0"
APP_EXE = "封面自动生成.exe"
APP_ICON = "app_icon.ico"
UNINSTALL_EXE = "Uninstall.exe"
PAYLOAD_MARKER = b'PYLD'

# Flat palette
BG       = "#fafafa"
CARD     = "#ffffff"
ACCENT   = "#4f6ef7"
ACCENT2  = "#3b5de7"
SUCCESS  = "#34d399"
TEXT     = "#111827"
TEXT2    = "#9ca3af"
INPUT_BG = "#f3f4f6"
LINE     = "#e5e7eb"


class SetupWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(False)
        self.root.geometry("500x460")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        # Center
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"500x460+{(sw-500)//2}+{(sh-460)//2}")

        # Icon
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            icon = os.path.join(base, APP_ICON)
            if os.path.exists(icon):
                self.root.iconbitmap(icon)
        except Exception:
            pass

        self.is_admin = self._is_admin()
        self.installed = False
        self.install_dir = self._default_dir()
        self.widgets = []  # track widgets for easy hide/show

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _is_admin():
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _default_dir(self):
        if self.is_admin:
            return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), APP_NAME)
        return os.path.join(os.environ.get("LOCALAPPDATA", os.environ.get("USERPROFILE", "")), APP_NAME)

    @staticmethod
    def _user_desktop():
        """Reliably get current user's Desktop path."""
        return os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")

    def _on_close(self):
        if self.installed:
            self.root.destroy()
            return
        if messagebox.askyesno(APP_NAME, "确定要取消安装吗？"):
            self.root.destroy()

    # ── helpers for creating flat widgets ───────────────────────────

    def _flat_btn(self, parent, text, cmd, bg=ACCENT, fg="white",
                  font_size=11, bold=True, width=None, pady=9):
        weight = "bold" if bold else "normal"
        btn = tk.Label(parent, text=text,
                       font=("Microsoft YaHei UI", font_size, weight),
                       bg=bg, fg=fg, cursor="hand2",
                       padx=(20 if not width else 0), pady=pady)
        if width:
            btn.config(width=width)
        btn.bind("<Button-1>", lambda e: cmd())
        darker = self._darken(bg, 0.12)
        btn.bind("<Enter>", lambda e: btn.config(bg=darker))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    @staticmethod
    def _darken(hex_color, amount=0.15):
        """Darken a hex color."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r, g, b = int(r * (1 - amount)), int(g * (1 - amount)), int(b * (1 - amount))
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Content container (for hide/show) ─────────────────────
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(fill="both", expand=True)

        # ── Top: Logo + Title ─────────────────────────────────────
        top = tk.Frame(self.content, bg=BG)
        top.pack(fill="x", pady=(32, 0))

        # App icon: black rounded + white "fm"
        c = tk.Canvas(top, width=56, height=56, bg=BG, highlightthickness=0)
        c.pack()
        c.create_oval(2, 2, 54, 54, fill="#141414", outline="")
        c.create_text(28, 29, text="fm", fill="white", font=("Arial", 18, "bold"))

        tk.Label(top, text=APP_NAME,
                 font=("Microsoft YaHei UI", 18, "bold"), bg=BG, fg=TEXT
                 ).pack(pady=(14, 3))
        tk.Label(top, text="PSD 批量封面自动生成工具",
                 font=("Microsoft YaHei UI", 10), bg=BG, fg=TEXT2
                 ).pack(pady=(0, 28))

        # ── Separator ─────────────────────────────────────────────
        tk.Frame(self.content, bg=LINE, height=1).pack(fill="x", padx=36)

        # ── Install path ──────────────────────────────────────────
        path_area = tk.Frame(self.content, bg=BG)
        path_area.pack(fill="x", padx=36, pady=(22, 0))

        tk.Label(path_area, text="安装位置",
                 font=("Microsoft YaHei UI", 9), bg=BG, fg=TEXT2
                 ).pack(anchor="w")

        path_row = tk.Frame(path_area, bg=CARD, highlightthickness=1,
                            highlightbackground=LINE, highlightcolor=ACCENT)
        path_row.pack(fill="x", pady=(6, 0), ipady=1)

        self.dir_var = tk.StringVar(value=self.install_dir)
        ent = tk.Entry(path_row, textvariable=self.dir_var,
                       font=("Consolas", 9), relief="flat", bd=0,
                       bg=CARD, fg=TEXT, highlightthickness=0,
                       insertbackground=ACCENT, insertwidth=2)
        ent.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=8)

        browse = tk.Label(path_row, text="  更改  ", font=("Microsoft YaHei UI", 9),
                          bg=INPUT_BG, fg=TEXT2, cursor="hand2")
        browse.pack(side="right", padx=6, pady=6)
        browse.bind("<Button-1>", lambda e: self._browse())
        browse.bind("<Enter>", lambda e: browse.config(bg="#e5e7eb", fg=TEXT))
        browse.bind("<Leave>", lambda e: browse.config(bg=INPUT_BG, fg=TEXT2))

        # ── Options (flat checkboxes) ─────────────────────────────
        opt_area = tk.Frame(self.content, bg=BG)
        opt_area.pack(fill="x", padx=36, pady=(20, 0))

        self.chk_desktop = tk.BooleanVar(value=True)
        self.chk_start = tk.BooleanVar(value=True)
        self.chk_run = tk.BooleanVar(value=True)

        for i, (text, var) in enumerate([
            ("创建桌面快捷方式", self.chk_desktop),
            ("创建开始菜单快捷方式", self.chk_start),
            ("安装后立即运行", self.chk_run),
        ]):
            row = tk.Frame(opt_area, bg=BG, cursor="hand2")
            row.pack(fill="x", pady=3)
            row.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))

            # Custom checkbox visual
            self._cb_box = tk.Canvas(row, width=16, height=16, bg=BG, highlightthickness=0)
            self._cb_box.pack(side="left")
            self._cb_box.create_rectangle(1, 1, 15, 15, fill=CARD, outline=LINE, width=1, tags="bg")
            check_id = self._cb_box.create_text(8, 8, text="", fill="white", font=("Arial", 10, "bold"), tags="check")
            tk.Label(row, text=text, font=("Microsoft YaHei UI", 9),
                     bg=BG, fg=TEXT, cursor="hand2").pack(side="left", padx=(8, 0))
            # Bind toggle
            row.bind("<Button-1>", lambda e, v=var, c=self._cb_box, cid=check_id: (
                v.set(not v.get()),
                c.itemconfig(cid, text="✓" if v.get() else ""),
                c.itemconfig("bg", fill=ACCENT if v.get() else CARD, outline=ACCENT if v.get() else LINE)
            ))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, v=var, c=self._cb_box, cid=check_id: (
                    v.set(not v.get()),
                    c.itemconfig(cid, text="✓" if v.get() else ""),
                    c.itemconfig("bg", fill=ACCENT if v.get() else CARD, outline=ACCENT if v.get() else LINE)
                ))
            # Init checked state
            var.trace_add("write", lambda *a, v=var, c=self._cb_box, cid=check_id: (
                c.itemconfig(cid, text="✓" if v.get() else ""),
                c.itemconfig("bg", fill=ACCENT if v.get() else CARD, outline=ACCENT if v.get() else LINE)
            ))
            # Set initial visual
            self._cb_box.itemconfig(check_id, text="✓")
            self._cb_box.itemconfig("bg", fill=ACCENT, outline=ACCENT)

        # ── Progress bar (hidden) ─────────────────────────────────
        self.pbar = ttk.Progressbar(self.content, length=428, mode="determinate")
        self.pbar_info = tk.Frame(self.content, bg=BG)
        self.status_lbl = tk.Label(self.pbar_info, text="",
                                   font=("Microsoft YaHei UI", 9), bg=BG, fg=TEXT2)
        self.status_lbl.pack(side="left")
        self.pct_lbl = tk.Label(self.pbar_info, text="",
                                font=("Microsoft YaHei UI", 9), bg=BG, fg=TEXT2)
        self.pct_lbl.pack(side="right")

        # ── Buttons ───────────────────────────────────────────────
        self.btn_install = self._flat_btn(self.content, "立即安装", self._start_install)
        self.btn_install.pack(fill="x", padx=36, pady=(26, 0), ipady=3)

        self.btn_cancel = self._flat_btn(self.content, "取消", self._on_close,
                                         bg=CARD, fg=TEXT2, bold=False, font_size=9, pady=6)
        self.btn_cancel.pack(fill="x", padx=36, pady=(8, 0), ipady=3)

        # Admin note
        if not self.is_admin:
            tk.Label(self.content, text="非管理员模式 · 安装到用户目录",
                     font=("Microsoft YaHei UI", 8), bg=BG, fg="#d1d5db"
                     ).pack(pady=(10, 0))

    def _browse(self):
        d = filedialog.askdirectory(title="选择安装位置", initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    # ── Install ─────────────────────────────────────────────────────

    def _start_install(self):
        target = self.dir_var.get().strip()
        if not target:
            messagebox.showerror(APP_NAME, "请选择安装位置")
            return
        self.install_dir = target

        # Hide buttons, show progress
        self.btn_install.pack_forget()
        self.btn_cancel.pack_forget()
        self.pbar.pack(pady=(20, 4), padx=36, fill="x")
        self.pbar_info.pack(fill="x", padx=36)
        self._set_progress(0, "准备安装…")
        self.root.after(200, self._do_install)

    def _set_progress(self, val, text):
        self.pbar["value"] = val
        self.status_lbl.config(text=text)
        self.pct_lbl.config(text=f"{val}%")
        self.root.update_idletasks()

    def _do_install(self):
        try:
            inst = self.install_dir
            self._set_progress(5, "正在创建目录…")
            os.makedirs(inst, exist_ok=True)

            self._set_progress(10, "正在读取安装包…")
            payload = self._read_payload()
            if payload is None:
                messagebox.showerror(APP_NAME, "无法读取安装数据，文件可能已损坏。")
                self.root.destroy()
                return

            self._set_progress(20, "正在解压文件…")
            self._extract_zip(payload, inst)

            exe_path = os.path.join(inst, APP_EXE)

            self._set_progress(85, "正在创建快捷方式…")
            icon_path = os.path.join(inst, APP_ICON)
            if self.chk_desktop.get():
                desktop = self._user_desktop()
                self._make_lnk(exe_path, os.path.join(desktop, "封面自动生成.lnk"), icon_path)
            if self.chk_start.get():
                sm = os.path.join(os.environ.get("APPDATA", ""),
                                  r"Microsoft\Windows\Start Menu\Programs", APP_NAME)
                os.makedirs(sm, exist_ok=True)
                self._make_lnk(exe_path, os.path.join(sm, "封面自动生成.lnk"), icon_path)

            self._set_progress(90, "正在生成卸载程序…")
            self._write_uninstaller(inst)

            self._set_progress(95, "正在注册程序…")
            self._register_uninstall(inst)

            self._set_progress(100, "安装完成！")
            self.installed = True
            self.root.after(500, self._show_done)

        except Exception as exc:
            messagebox.showerror(APP_NAME, f"安装过程中发生错误：\n{exc}")
            self.root.destroy()

    # ── Done state ──────────────────────────────────────────────────

    def _show_done(self):
        self.content.destroy()

        done = tk.Frame(self.root, bg=BG)
        done.pack(fill="both", expand=True)

        # Checkmark
        c = tk.Canvas(done, width=64, height=64, bg=BG, highlightthickness=0)
        c.pack(pady=(50, 0))
        c.create_oval(2, 2, 62, 62, fill=SUCCESS, outline="")
        c.create_text(32, 33, text="✓", fill="white", font=("Arial", 28, "bold"))

        tk.Label(done, text="安装成功",
                 font=("Microsoft YaHei UI", 17, "bold"), bg=BG, fg=TEXT
                 ).pack(pady=(18, 6))
        tk.Label(done, text=self.install_dir,
                 font=("Consolas", 8), bg=BG, fg=TEXT2
                 ).pack()

        # Run button
        self._flat_btn(done, "打开应用", self._run_app,
                       bg=SUCCESS, width=30, pady=10).pack(pady=(28, 8))

        self._flat_btn(done, "完成", self.root.destroy,
                       bg=CARD, fg=TEXT2, bold=False, font_size=9, width=30, pady=6
                       ).pack(pady=(4, 0))

    def _run_app(self):
        exe = os.path.join(self.install_dir, APP_EXE)
        if os.path.isfile(exe):
            subprocess.Popen([exe], cwd=self.install_dir)
        self.root.destroy()

    # ── Core logic ──────────────────────────────────────────────────

    def _read_payload(self):
        try:
            base = getattr(sys, "_MEIPASS", None)
            if base:
                p = os.path.join(base, "payload.zip")
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return f.read()
        except Exception:
            pass

        exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
        if os.path.isfile(exe):
            try:
                with open(exe, "rb") as f:
                    f.seek(-8, 2)
                    if f.read(4) == PAYLOAD_MARKER:
                        size = struct.unpack("<I", f.read(4))[0]
                        if 0 < size < 500_000_000:
                            f.seek(-(8 + size), 2)
                            return f.read(size)
            except Exception:
                pass

        local = os.path.join(os.path.dirname(exe), "payload.zip")
        if os.path.isfile(local):
            with open(local, "rb") as f:
                return f.read()
        return None

    def _extract_zip(self, data, dest):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            members = zf.infolist()
            total = sum(m.file_size for m in members)
            done = 0
            for m in members:
                zf.extract(m, dest)
                done += m.file_size
                if total > 0:
                    pct = int(done / total * 100)
                    mapped = 20 + int(pct * 0.65)
                    self._set_progress(mapped, f"正在解压… {pct}%")

    def _make_lnk(self, target, shortcut, icon_path=None):
        """Create .lnk via PowerShell (more reliable than VBS for unicode paths)."""
        if icon_path is None:
            icon_path = target
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{shortcut}"); '
            f'$s.TargetPath = "{target}"; '
            f'$s.WorkingDirectory = "{os.path.dirname(target)}"; '
            f'$s.IconLocation = "{icon_path},0"; '
            f'$s.Description = "{APP_NAME}"; '
            f'$s.Save()'
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, timeout=15, encoding="utf-8",
            )
        except Exception:
            pass

    def _write_uninstaller(self, inst):
        """Copy Uninstall.exe from payload to install directory."""
        # The Uninstall.exe is embedded in the payload.zip
        uninstall_src = None
        try:
            payload = self._read_payload()
            if payload:
                import zipfile, io
                zf = zipfile.ZipFile(io.BytesIO(payload))
                for name in zf.namelist():
                    if name == "Uninstall.exe":
                        data = zf.read(name)
                        uninstall_path = os.path.join(inst, UNINSTALL_EXE)
                        with open(uninstall_path, "wb") as f:
                            f.write(data)
                        return
        except Exception:
            pass

    def _register_uninstall(self, inst):
        try:
            import winreg
            root = winreg.HKEY_LOCAL_MACHINE if self.is_admin else winreg.HKEY_CURRENT_USER
            path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\封面自动生成 v2.0"
            key = winreg.CreateKeyEx(root, path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "2.0.0")
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "PSD Cover Tool")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, inst)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, os.path.join(inst, UNINSTALL_EXE))
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, os.path.join(inst, APP_EXE))
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
        except Exception:
            pass


if __name__ == "__main__":
    SetupWizard()
