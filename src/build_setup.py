#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script for 封面自动生成 v2.0 Setup installer.
Creates a professional single-file Setup.exe with embedded payload.
"""

import os
import sys
import subprocess
import shutil
import zipfile
import struct

# Paths
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
PORTABLE_EXE = os.path.join(
    os.environ.get("USERPROFILE", ""),
    "Desktop",
    "封面自动生成 v2.0",
    "便携版",
    "封面自动生成.exe",
)
ICON_PATH = os.path.join(WORKSPACE, "app_icon.ico")
INSTALLER_PY = os.path.join(WORKSPACE, "installer.py")
UNINSTALLER_PY = os.path.join(WORKSPACE, "uninstaller.py")
DESKTOP = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
OUTPUT_FOLDER = os.path.join(DESKTOP, "封面自动生成 v2.0")
OUTPUT_EXE = os.path.join(OUTPUT_FOLDER, "封面自动生成v2.0.Setup.exe")
PAYLOAD_ZIP = os.path.join(WORKSPACE, "payload.zip")

BUILD_DIR = os.path.join(WORKSPACE, "build_setup")
DIST_DIR = os.path.join(WORKSPACE, "dist_setup")
UNINSTALL_BUILD = os.path.join(WORKSPACE, "build_uninstall")
UNINSTALL_DIST = os.path.join(WORKSPACE, "dist_uninstall")


def check_files():
    for p, name in [(PORTABLE_EXE, "便携版 exe"), (ICON_PATH, "app_icon.ico"),
                     (INSTALLER_PY, "installer.py"), (UNINSTALLER_PY, "uninstaller.py")]:
        if not os.path.isfile(p):
            print(f"[ERROR] {name} not found: {p}")
            sys.exit(1)
    print(f"[OK] 便携版 exe: {os.path.getsize(PORTABLE_EXE) / 1048576:.1f} MB")
    print(f"[OK] Icon: {ICON_PATH}")
    print(f"[OK] Uninstaller: {UNINSTALLER_PY}")


def build_uninstaller():
    """Build Uninstall.exe as a standalone executable."""
    print("\n[1/5] Building Uninstall.exe ...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "Uninstall",
        "--icon", ICON_PATH,
        "--add-data", f"{ICON_PATH};.",
        "--distpath", UNINSTALL_DIST,
        "--workpath", UNINSTALL_BUILD,
        "--specpath", WORKSPACE,
        "--noconfirm",
        UNINSTALLER_PY,
    ]
    result = subprocess.run(cmd, cwd=WORKSPACE)
    if result.returncode != 0:
        print("[ERROR] Uninstaller build failed!")
        sys.exit(1)
    uninstall_exe = os.path.join(UNINSTALL_DIST, "Uninstall.exe")
    if not os.path.isfile(uninstall_exe):
        print("[ERROR] Uninstall.exe not found!")
        sys.exit(1)
    print(f"  Uninstall.exe = {os.path.getsize(uninstall_exe) / 1048576:.1f} MB")
    return uninstall_exe


def create_payload():
    print("\n[2/5] Creating payload.zip ...")
    uninstall_exe = os.path.join(UNINSTALL_DIST, "Uninstall.exe")
    with zipfile.ZipFile(PAYLOAD_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(PORTABLE_EXE, "封面自动生成.exe")
        zf.write(ICON_PATH, "app_icon.ico")
        if os.path.isfile(uninstall_exe):
            zf.write(uninstall_exe, "Uninstall.exe")
    sz = os.path.getsize(PAYLOAD_ZIP) / 1048576
    print(f"  payload.zip = {sz:.1f} MB (includes Uninstall.exe)")


def build_installer():
    print("\n[3/5] Building Setup.exe with PyInstaller ...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "封面自动生成v2.0.Setup",
        "--icon", ICON_PATH,
        "--add-data", f"{ICON_PATH};.",
        "--add-data", f"{PAYLOAD_ZIP};.",
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "--specpath", WORKSPACE,
        "--noconfirm",
        INSTALLER_PY,
    ]
    print("  " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=WORKSPACE)
    if result.returncode != 0:
        print("[ERROR] PyInstaller build failed!")
        sys.exit(1)

    src = os.path.join(DIST_DIR, "封面自动生成v2.0.Setup.exe")
    if not os.path.isfile(src):
        print("[ERROR] Output exe not found!")
        sys.exit(1)
    print(f"  Build OK: {os.path.getsize(src) / 1048576:.1f} MB")
    return src


def deliver(src):
    print("\n[4/5] Delivering to desktop ...")
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    # Remove old installer if exists
    if os.path.exists(OUTPUT_EXE):
        os.remove(OUTPUT_EXE)
    shutil.move(src, OUTPUT_EXE)
    sz = os.path.getsize(OUTPUT_EXE) / 1048576
    print(f"  -> {OUTPUT_EXE}")
    print(f"     Size: {sz:.1f} MB")


def cleanup():
    print("\n[5/5] Cleaning up ...")
    for d in [BUILD_DIR, DIST_DIR, UNINSTALL_BUILD, UNINSTALL_DIST]:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    if os.path.isfile(PAYLOAD_ZIP):
        os.remove(PAYLOAD_ZIP)
    # Remove .spec files
    for spec_name in ["封面自动生成v2.0.Setup.spec", "Uninstall.spec"]:
        spec = os.path.join(WORKSPACE, spec_name)
        if os.path.isfile(spec):
            os.remove(spec)
    print("  Done.")


if __name__ == "__main__":
    print("=" * 50)
    print("  封面自动生成 v2.0 - Setup Builder")
    print("=" * 50)
    check_files()
    build_uninstaller()
    create_payload()
    src = build_installer()
    deliver(src)
    cleanup()
    print("\n✓ Build complete!")
    print(f"  Output: {OUTPUT_EXE}")
