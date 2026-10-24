#!/usr/bin/env python3
"""Probe an actual desktop OpenGL context on Windows, before any FreeCAD build.

Informational unless --require-minimum is set. Never counts as GUI acceptance.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import platform
import re
import sys

PFD_DRAW_TO_WINDOW = 0x00000004
PFD_SUPPORT_OPENGL = 0x00000020
PFD_DOUBLEBUFFER = 0x00000001
PFD_TYPE_RGBA = 0
PFD_MAIN_PLANE = 0


class PIXELFORMATDESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("nSize", wintypes.WORD), ("nVersion", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("iPixelType", ctypes.c_ubyte),
        ("cColorBits", ctypes.c_ubyte), ("cRedBits", ctypes.c_ubyte),
        ("cRedShift", ctypes.c_ubyte), ("cGreenBits", ctypes.c_ubyte),
        ("cGreenShift", ctypes.c_ubyte), ("cBlueBits", ctypes.c_ubyte),
        ("cBlueShift", ctypes.c_ubyte), ("cAlphaBits", ctypes.c_ubyte),
        ("cAlphaShift", ctypes.c_ubyte), ("cAccumBits", ctypes.c_ubyte),
        ("cAccumRedBits", ctypes.c_ubyte), ("cAccumGreenBits", ctypes.c_ubyte),
        ("cAccumBlueBits", ctypes.c_ubyte), ("cAccumAlphaBits", ctypes.c_ubyte),
        ("cDepthBits", ctypes.c_ubyte), ("cStencilBits", ctypes.c_ubyte),
        ("cAuxBuffers", ctypes.c_ubyte), ("iLayerType", ctypes.c_ubyte),
        ("bReserved", ctypes.c_ubyte), ("dwLayerMask", wintypes.DWORD),
        ("dwVisibleMask", wintypes.DWORD), ("dwDamageMask", wintypes.DWORD),
    ]


def version_tuple(value):
    match = re.match(r"^\s*(\d+)\.(\d+)", value or "")
    return tuple(map(int, match.groups())) if match else None


def probe():
    if os.name != "nt":
        raise RuntimeError("Native Windows graphical runner required")
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    ogl = ctypes.WinDLL("opengl32", use_last_error=True)

    user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user.CreateWindowExW.restype = wintypes.HWND
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.DestroyWindow.argtypes = [wintypes.HWND]
    gdi.ChoosePixelFormat.argtypes = [wintypes.HDC, ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
    gdi.ChoosePixelFormat.restype = ctypes.c_int
    gdi.SetPixelFormat.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
    gdi.SetPixelFormat.restype = wintypes.BOOL
    ogl.wglCreateContext.argtypes = [wintypes.HDC]
    ogl.wglCreateContext.restype = wintypes.HGLRC if hasattr(wintypes, "HGLRC") else ctypes.c_void_p
    ogl.wglMakeCurrent.argtypes = [wintypes.HDC, ctypes.c_void_p]
    ogl.wglMakeCurrent.restype = wintypes.BOOL
    ogl.wglDeleteContext.argtypes = [ctypes.c_void_p]
    ogl.glGetString.argtypes = [ctypes.c_uint]
    ogl.glGetString.restype = ctypes.c_char_p

    hwnd = user.CreateWindowExW(0, "STATIC", "3117 OpenGL Capability Probe", 0,
                                0, 0, 32, 32, None, None, None, None)
    if not hwnd:
        raise RuntimeError(f"CreateWindowExW failed: {ctypes.get_last_error()}")
    dc = None
    context = None
    try:
        dc = user.GetDC(hwnd)
        if not dc:
            raise RuntimeError(f"GetDC failed: {ctypes.get_last_error()}")
        pfd = PIXELFORMATDESCRIPTOR()
        pfd.nSize = ctypes.sizeof(PIXELFORMATDESCRIPTOR)
        pfd.nVersion = 1
        pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER
        pfd.iPixelType = PFD_TYPE_RGBA
        pfd.cColorBits = 24
        pfd.cDepthBits = 24
        pfd.iLayerType = PFD_MAIN_PLANE
        choice = gdi.ChoosePixelFormat(dc, ctypes.byref(pfd))
        if choice == 0 or not gdi.SetPixelFormat(dc, choice, ctypes.byref(pfd)):
            raise RuntimeError(f"No usable OpenGL pixel format: {ctypes.get_last_error()}")
        context = ogl.wglCreateContext(dc)
        if not context or not ogl.wglMakeCurrent(dc, context):
            raise RuntimeError(f"OpenGL context creation failed: {ctypes.get_last_error()}")
        def gl_string(name):
            item = ogl.glGetString(name)
            return item.decode("utf-8", errors="replace") if item else None
        return {"version": gl_string(0x1F02), "vendor": gl_string(0x1F00),
                "renderer": gl_string(0x1F01), "pixel_format": choice}
    finally:
        if context:
            ogl.wglMakeCurrent(None, None)
            ogl.wglDeleteContext(context)
        if dc:
            user.ReleaseDC(hwnd, dc)
        user.DestroyWindow(hwnd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-minimum", action="store_true")
    args = parser.parse_args()
    report = {"schema": 1, "kind": "windows_opengl_capability_probe",
              "system": platform.system(), "windows_gui_acceptance": "not_executed",
              "release_ready": False, "minimum_version": "2.0"}
    try:
        report.update(probe())
        parsed = version_tuple(report["version"])
        report["status"] = "compatible_for_further_gui_testing" if parsed and parsed >= (2, 0) else "incompatible"
    except Exception as exc:
        report.update(status="probe_failed", error=str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if not args.require_minimum or report["status"] == "compatible_for_further_gui_testing" else 2


if __name__ == "__main__":
    sys.exit(main())
