#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面自动生成 v2.0 — 扁平化卸载向导"""

import tkinter as tk
import os
import sys
import subprocess
import threading
import winreg

APP_NAME = "封面自动生成 v2.0"
APP_EXE = "封面自动生成.exe"
APP_ICON = "app_icon.ico"
UNINSTALL_EXE = "Uninstall.exe"

# Colors
BG = "#F5F5F5"
PANEL = "#EBEBEB"
TXT = "#1A1A1A"
DIM = "#888888"
RED = "#E74C3C"
DARK = "#C0392B"
CARD = "#FFFFFF"
BDR = "#CCCCCC"


class UninstallWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"卸载 {APP_NAME}")
        self.root.geometry("440x340")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        # Center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 440) // 2
        y = (self.root.winfo_screenheight() - 340) // 2
        self.root.geometry(f"440x340+{x}+{y}")

        self._set_icon()
        self.inst_dir = self._find_install_dir()
        self._build_ui()

    def _set_icon(self):
        """Set window icon."""
        try:
            if getattr(sys, 'frozen', False):
                base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base, APP_ICON)
            if os.path.isfile(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

    def _find_install_dir(self):
        """Find install directory from registry or exe location."""
        # If running from install dir
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isfile(os.path.join(exe_dir, APP_EXE)):
                return exe_dir

        # Try registry
        for root_key in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            try:
                path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\封面自动生成 v2.0"
                key = winreg.OpenKey(root_key, path, 0, winreg.KEY_READ)
                inst, _ = winreg.QueryValueEx(key, "InstallLocation")
                winreg.CloseKey(key)
                if inst and os.path.isdir(inst):
                    return inst
            except Exception:
                pass

        return ""

    def _build_ui(self):
        # Main content frame
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        # Icon
        c = tk.Canvas(body, width=56, height=56, bg=BG, highlightthickness=0)
        c.pack(pady=(0, 16))
        c.create_oval(2, 2, 54, 54, fill="#141414", outline="")
        c.create_text(28, 29, text="fm", fill="white", font=("Arial", 18, "bold"))

        # Title
        tk.Label(body, text=f"卸载 {APP_NAME}",
                 bg=BG, fg=TXT, font=("Microsoft YaHei UI", 16, "bold")).pack(pady=(0, 8))

        # Description
        if self.inst_dir:
            desc = f"将从以下位置移除所有文件：\n{self.inst_dir}"
        else:
            desc = "未检测到安装信息，是否继续？"
        tk.Label(body, text=desc, bg=BG, fg=DIM,
                 font=("Microsoft YaHei UI", 10), justify=tk.CENTER, wraplength=360).pack(pady=(0, 24))

        # Button frame
        btn_frame = tk.Frame(body, bg=BG)
        btn_frame.pack(fill=tk.X)

        # Cancel button
        tk.Button(btn_frame, text="取消", command=self._cancel,
                  bg=CARD, fg=TXT, activebackground=BDR,
                  font=("Microsoft YaHei UI", 10), relief=tk.FLAT,
                  padx=20, pady=6, cursor="hand2").pack(side=tk.RIGHT, padx=(8, 0))

        # Uninstall button
        self.uninstall_btn = tk.Button(
            btn_frame, text="卸载", command=self._start_uninstall,
            bg=RED, fg="white", activebackground=DARK,
            font=("Microsoft YaHei UI", 10, "bold"), relief=tk.FLAT,
            padx=24, pady=6, cursor="hand2")
        self.uninstall_btn.pack(side=tk.RIGHT)

        # Progress area (hidden initially)
        self.progress_frame = tk.Frame(self.root, bg=BG)
        self.progress_bar = tk.Canvas(self.progress_frame, width=360, height=8,
                                       bg=PANEL, highlightthickness=0)
        self.progress_bar.pack(pady=(0, 8))
        self.progress_label = tk.Label(self.progress_frame, text="正在卸载...",
                                        bg=BG, fg=DIM, font=("Microsoft YaHei UI", 10))
        self.progress_label.pack()

        # Success area (hidden initially)
        self.success_frame = tk.Frame(self.root, bg=BG)

        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self.root.mainloop()

    def _cancel(self):
        self.root.destroy()

    def _start_uninstall(self):
        # Switch to progress UI
        for w in self.root.winfo_children():
            w.destroy()

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)

        tk.Label(body, text="正在卸载…", bg=BG, fg=TXT,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(0, 20))

        self.progress_bar = tk.Canvas(body, width=360, height=8,
                                       bg=PANEL, highlightthickness=0)
        self.progress_bar.pack(pady=(0, 12))

        self.progress_label = tk.Label(body, text="准备中…", bg=BG, fg=DIM,
                                        font=("Microsoft YaHei UI", 10))
        self.progress_label.pack()

        # Run uninstall in thread
        t = threading.Thread(target=self._uninstall_worker, daemon=True)
        t.start()

    def _set_progress(self, pct, text):
        self.root.after(0, self._update_progress_ui, pct, text)

    def _update_progress_ui(self, pct, text):
        if not hasattr(self, 'progress_bar') or not self.progress_bar.winfo_exists():
            return
        self.progress_label.config(text=text)
        self.progress_bar.delete("all")
        w = 360
        fill_w = int(w * pct / 100)
        if fill_w > 0:
            self.progress_bar.create_rectangle(0, 0, fill_w, 8, fill=RED, outline="")

    def _uninstall_worker(self):
        inst = self.inst_dir
        user_desktop = self._user_desktop()
        start_menu = os.path.join(os.environ.get("APPDATA", ""),
                                   r"Microsoft\Windows\Start Menu\Programs", APP_NAME)

        # Step 1: Kill running process
        self._set_progress(10, "正在关闭程序…")
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", APP_EXE],
                capture_output=True, timeout=10
            )
        except Exception:
            pass

        # Step 2: Remove shortcuts
        self._set_progress(30, "正在删除快捷方式…")
        try:
            lnk = os.path.join(user_desktop, "封面自动生成.lnk")
            if os.path.isfile(lnk):
                os.remove(lnk)
        except Exception:
            pass
        try:
            if os.path.isdir(start_menu):
                import shutil
                shutil.rmtree(start_menu, ignore_errors=True)
        except Exception:
            pass

        # Step 3: Remove registry entry
        self._set_progress(50, "正在清理注册表…")
        for root_key in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            try:
                path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\封面自动生成 v2.0"
                winreg.DeleteKey(root_key, path)
            except Exception:
                pass

        # Step 4: Remove install directory
        self._set_progress(70, "正在删除文件…")
        try:
            import shutil
            if inst and os.path.isdir(inst):
                shutil.rmtree(inst, ignore_errors=True)
        except Exception:
            pass

        # Step 5: Clean up self (the uninstall exe might still be running)
        self._set_progress(90, "正在完成…")

        # Schedule self-deletion after exit
        self_exe = sys.executable if getattr(sys, 'frozen', False) else ""
        if self_exe and os.path.isfile(self_exe):
            try:
                subprocess.Popen(
                    ["cmd", "/c", "ping", "127.0.0.1", "-n", "2", ">nul",
                     "&", "del", "/f", "/q", self_exe],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                pass

        self._set_progress(100, "卸载完成")

        # Show success
        self.root.after(500, self._show_success)

    def _show_success(self):
        if not self.root.winfo_exists():
            return
        for w in self.root.winfo_children():
            w.destroy()

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        # Green checkmark
        c = tk.Canvas(body, width=56, height=56, bg=BG, highlightthickness=0)
        c.pack(pady=(0, 16))
        c.create_oval(2, 2, 54, 54, fill="#27AE60", outline="")
        c.create_text(28, 30, text="✓", fill="white", font=("Arial", 26, "bold"))

        tk.Label(body, text=f"{APP_NAME} 已成功卸载",
                 bg=BG, fg=TXT, font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(0, 24))

        tk.Button(body, text="关闭", command=self.root.destroy,
                  bg=CARD, fg=TXT, activebackground=BDR,
                  font=("Microsoft YaHei UI", 10), relief=tk.FLAT,
                  padx=30, pady=6, cursor="hand2").pack()

    def _user_desktop(self):
        return os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")


if __name__ == "__main__":
    UninstallWizard()
