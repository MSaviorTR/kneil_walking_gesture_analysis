"""
KNEIL 3D Motion Viewer — Motion Picker & Launcher (tkinter only).
   launcher 1.0, 23 Nov 2026

Provides a single desktop window listing all 50 KNEIL motions grouped by source
(with friendly aliases pinned on top), live search, options (speed, implant CAD,
see-through right leg), and actions:
  - Open 3D viewer (also on double-click; picker stays open after closing viewer)
  - Save PNG at time t (--render)
  - Render Blender clip (background export + Blender 5.2 render; opens folder when done)

Works both from Python (`python viewer/launcher.py`) and as a standalone PyInstaller
Windows executable (`dist/KNEIL_viewer/KNEIL_viewer.exe`) with no G: or repo needed.
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

VERSION = 'launcher 1.0'

# Ensure viewer/ and pipeline/ are importable when run from Python
if not getattr(sys, 'frozen', False):
    _VIEWER_DIR = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(_VIEWER_DIR)
    for _d in (_VIEWER_DIR, os.path.join(_REPO_ROOT, 'pipeline')):
        if _d not in sys.path:
            sys.path.insert(0, _d)

import kneil_viewer as KV

LOG_PATH = os.path.join(KV.CACHE_DIR, 'launcher_log.txt')
SOURCE_ORDER = ('old viewer', 'Camargo replay', 'v1.6 generator')


def log_msg(msg):
    os.makedirs(KV.CACHE_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    try:
        print(line, flush=True)
    except Exception:
        pass
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def find_blender():
    """Return path to blender.exe if installed, else None."""
    cands = [
        os.environ.get('KNEIL_BLENDER_EXE', ''),
        r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe',
        r'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe',
        r'C:\Program Files\Blender Foundation\Blender 4.3\blender.exe',
        r'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe',
    ]
    for p in cands:
        if p and os.path.isfile(p):
            return p
    w = shutil.which('blender')
    return w if w and os.path.isfile(w) else None


def find_blender_script():
    """Return path to viewer/blender_render.py (repo or bundled_data)."""
    bdir = KV.get_bundled_data_dir()
    if bdir:
        bp = os.path.join(bdir, 'blender_render.py')
        if os.path.isfile(bp):
            return bp
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, 'blender_render.py')
    return p if os.path.isfile(p) else None


def worker_cmd(*extra_args):
    """Build subprocess command to invoke this launcher in worker mode (frozen or Python)."""
    if getattr(sys, 'frozen', False):
        return [sys.executable, *extra_args]
    return [sys.executable, os.path.abspath(__file__), *extra_args]


def _run_worker_viewer(args):
    catalog = KV.build_catalog()
    entry = KV.resolve_motion_id(args.motion, catalog)
    KV.run_interactive(
        catalog, entry,
        speed=args.speed,
        use_cad=not args.no_cad,
        see_through=not args.no_see_through,
    )
    return 0


def _run_worker_render(args):
    catalog = KV.build_catalog()
    entry = KV.resolve_motion_id(args.motion, catalog)
    data = KV.load_motion(entry)
    KV.render_composite_png(
        data, args.t, args.out,
        use_cad=not args.no_cad,
        see_through=not args.no_see_through,
    )
    print(f'Rendered {args.out} ({entry["id"]} at t={args.t:.2f} s)', flush=True)
    return 0


def _run_worker_export(args):
    import export_motion as EM
    EM.export_motion(args.motion, args.out, fps=args.fps, t0=args.t0, max_s=args.length)
    return 0


class MotionPickerApp:
    def __init__(self, root, catalog):
        self.root = root
        self.catalog = catalog
        self.by_id = {c['id']: c for c in catalog}
        self.blender_exe = find_blender()
        self.blender_script = find_blender_script()
        self.item_to_id = {}

        root.title(f'KNEIL 3D Motion Viewer ({VERSION})')
        root.geometry('1120x680')
        root.minsize(920, 560)

        style = ttk.Style(root)
        for theme in ('vista', 'clam', 'default'):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure('Treeview', rowheight=24, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'))

        # --- Top header ---
        hdr = ttk.Frame(root, padding=(12, 10, 12, 6))
        hdr.pack(fill='x')
        ttk.Label(hdr, text='KNEIL 3D Motion Viewer', font=('Segoe UI', 14, 'bold')).pack(side='left')
        n_ok = sum(1 for c in catalog if c.get('available', True))
        mode_tag = 'standalone exe' if getattr(sys, 'frozen', False) else 'Python workspace'
        ttk.Label(
            hdr,
            text=f'{n_ok}/{len(catalog)} motions ready  |  {mode_tag}  |  {KV.VERSION}',
            foreground='#445566',
            font=('Segoe UI', 9),
        ).pack(side='right')

        # --- Search bar ---
        sbar = ttk.Frame(root, padding=(12, 0, 12, 6))
        sbar.pack(fill='x')
        ttk.Label(sbar, text='Search:').pack(side='left', padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *_: self.populate_tree())
        self.search_entry = ttk.Entry(sbar, textvariable=self.search_var, width=48)
        self.search_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(sbar, text='Clear', width=8, command=lambda: self.search_var.set('')).pack(side='left', padx=(6, 0))

        # --- Grouped motion list (Treeview) ---
        tframe = ttk.Frame(root, padding=(12, 0, 12, 6))
        tframe.pack(fill='both', expand=True)

        cols = ('id', 'dur', 'classes', 'split', 'status')
        self.tree = ttk.Treeview(tframe, columns=cols, show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='Motion (double-click to open 3D viewer)')
        self.tree.heading('id', text='ID / Alias')
        self.tree.heading('dur', text='Dur')
        self.tree.heading('classes', text='True classes')
        self.tree.heading('split', text='Split')
        self.tree.heading('status', text='Status')

        self.tree.column('#0', width=320, stretch=True)
        self.tree.column('id', width=215, stretch=False)
        self.tree.column('dur', width=62, anchor='e', stretch=False)
        self.tree.column('classes', width=185, stretch=False)
        self.tree.column('split', width=190, stretch=False)
        self.tree.column('status', width=110, stretch=False)

        self.tree.tag_configure('group', font=('Segoe UI', 9, 'bold'), foreground='#1b365d')
        self.tree.tag_configure('alias', foreground='#0b5394')
        self.tree.tag_configure('out_sample', foreground='#1f6f3d')
        self.tree.tag_configure('disabled', foreground='#999999')

        ysb = ttk.Scrollbar(tframe, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.bind('<Return>', self.on_double_click)

        # --- Options bar ---
        opt = ttk.LabelFrame(root, text='Viewer options', padding=(10, 6))
        opt.pack(fill='x', padx=12, pady=(0, 6))

        ttk.Label(opt, text='Playback speed:').pack(side='left', padx=(0, 4))
        self.speed_var = tk.StringVar(value='1.0x')
        speed_cb = ttk.Combobox(
            opt, textvariable=self.speed_var, width=7, state='readonly',
            values=('0.25x', '0.5x', '1.0x', '1.5x', '2.0x'),
        )
        speed_cb.pack(side='left', padx=(0, 18))

        self.cad_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text='Implant CAD (3 parts)', variable=self.cad_var).pack(side='left', padx=(0, 18))

        self.seethrough_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text='See-through right leg', variable=self.seethrough_var).pack(side='left', padx=(0, 18))

        # --- Actions bar ---
        act = ttk.Frame(root, padding=(12, 2, 12, 8))
        act.pack(fill='x')

        self.btn_open = ttk.Button(act, text='Open 3D viewer', command=self.on_open_viewer)
        self.btn_open.pack(side='left', padx=(0, 14))

        ttk.Separator(act, orient='vertical').pack(side='left', fill='y', padx=(0, 14))

        ttk.Label(act, text='t (s):').pack(side='left', padx=(0, 4))
        self.t_var = tk.StringVar(value='8.0')
        ttk.Entry(act, textvariable=self.t_var, width=6).pack(side='left', padx=(0, 6))
        self.btn_png = ttk.Button(act, text='Save PNG at time t', command=self.on_save_png)
        self.btn_png.pack(side='left', padx=(0, 14))

        ttk.Separator(act, orient='vertical').pack(side='left', fill='y', padx=(0, 14))

        ttk.Label(act, text='Start (s):').pack(side='left', padx=(0, 4))
        self.bl_t0_var = tk.StringVar(value='4.0')
        ttk.Entry(act, textvariable=self.bl_t0_var, width=5).pack(side='left', padx=(0, 8))
        ttk.Label(act, text='Length (s):').pack(side='left', padx=(0, 4))
        self.bl_len_var = tk.StringVar(value='2.0')
        ttk.Entry(act, textvariable=self.bl_len_var, width=5).pack(side='left', padx=(0, 6))

        self.btn_blender = ttk.Button(act, text='Render Blender clip', command=self.on_render_blender)
        self.btn_blender.pack(side='left')
        if not self.blender_exe or not self.blender_script:
            self.btn_blender.configure(state='disabled')
            ttk.Label(
                act, text='(Blender not found)', foreground='#884444', font=('Segoe UI', 8, 'italic')
            ).pack(side='left', padx=(6, 0))

        # --- Status bar ---
        sbar_bot = ttk.Frame(root, padding=(12, 4, 12, 8))
        sbar_bot.pack(fill='x')
        self.status_var = tk.StringVar(value=f'Ready. Select a motion and click "Open 3D viewer" (log: {LOG_PATH})')
        ttk.Label(sbar_bot, textvariable=self.status_var, foreground='#334455', font=('Segoe UI', 8)).pack(side='left')

        self.populate_tree()

    def _matches(self, c, q, alias=None):
        if not q:
            return True
        hay = ' '.join([
            c['id'], c['name'], c['source'], c.get('in_sample_label', ''),
            ' '.join(c.get('true_labels', [])), alias or '',
        ]).lower()
        return all(tok in hay for tok in q.split())

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.item_to_id.clear()
        q = self.search_var.get().strip().lower()

        # 1. Friendly aliases pinned on top
        alias_items = []
        for al, mid in KV.ALIASES.items():
            if mid in self.by_id and self._matches(self.by_id[mid], q, alias=al):
                alias_items.append((al, self.by_id[mid]))
        if alias_items:
            g_al = self.tree.insert('', 'end', text=f'Friendly aliases ({len(alias_items)})', open=True, tags=('group',))
            for al, c in alias_items:
                self._insert_motion(g_al, c, label=f'{al}  —  {c["name"]}', id_col=al, extra_tag='alias')

        # 2. All 50 motions grouped by source
        for src in SOURCE_ORDER:
            items = [c for c in self.catalog if c['source'] == src and self._matches(c, q)]
            if not items:
                continue
            g = self.tree.insert('', 'end', text=f'{src} ({len(items)})', open=True, tags=('group',))
            for c in items:
                self._insert_motion(g, c, label=c['name'], id_col=c['id'])

        # Select first motion row automatically
        for grp in self.tree.get_children():
            kids = self.tree.get_children(grp)
            if kids:
                self.tree.selection_set(kids[0])
                self.tree.focus(kids[0])
                break

    def _insert_motion(self, parent, c, label, id_col, extra_tag=None):
        avail = c.get('available', True)
        split_short = 'in-sample' if c.get('in_sample', True) else 'out-of-sample'
        classes = ', '.join(c.get('true_labels', []))
        status = 'ready' if avail else c.get('unavailable_reason', 'missing')
        tags = []
        if not avail:
            tags.append('disabled')
        else:
            if extra_tag:
                tags.append(extra_tag)
            if not c.get('in_sample', True):
                tags.append('out_sample')
        iid = self.tree.insert(
            parent, 'end', text=label,
            values=(id_col, f'{c["dur"]:.1f} s', classes, split_short, status),
            tags=tuple(tags),
        )
        self.item_to_id[iid] = c['id']

    def _selected_entry(self):
        sel = self.tree.selection()
        if not sel:
            return None
        mid = self.item_to_id.get(sel[0])
        if not mid:
            return None
        c = self.by_id[mid]
        if not c.get('available', True):
            messagebox.showwarning(
                'Motion unavailable',
                f'"{c["name"]}" cannot be opened:\n{c.get("unavailable_reason", "Source missing")}',
            )
            return None
        return c

    def _option_flags(self):
        flags = []
        if not self.cad_var.get():
            flags.append('--no-cad')
        if not self.seethrough_var.get():
            flags.append('--no-see-through')
        return flags

    def on_double_click(self, _event=None):
        if self._selected_entry() is not None:
            self.on_open_viewer()

    def on_open_viewer(self):
        c = self._selected_entry()
        if c is None:
            return
        spd = float(self.speed_var.get().rstrip('x'))
        cmd = worker_cmd('--worker-viewer', c['id'], '--speed', str(spd), *self._option_flags())
        log_msg(f'Launching 3D viewer: {cmd}')
        self.status_var.set(f'3D viewer open: {c["name"]} ({c["id"]}) — close viewer window to continue...')

        def _watch():
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or f'Exit code {proc.returncode}').strip()
                    log_msg(f'Viewer error ({c["id"]}): {err}')
                    self.root.after(0, lambda: self._show_error('3D viewer failed', err))
                else:
                    log_msg(f'3D viewer closed cleanly ({c["id"]})')
                    self.root.after(0, lambda: self.status_var.set(f'Ready. Closed 3D viewer ({c["id"]}).'))
            except Exception as exc:
                tb = traceback.format_exc()
                log_msg(f'Viewer launch exception: {tb}')
                self.root.after(0, lambda: self._show_error('Failed to launch 3D viewer', str(exc)))

        threading.Thread(target=_watch, daemon=True).start()

    def on_save_png(self):
        c = self._selected_entry()
        if c is None:
            return
        try:
            t_val = float(self.t_var.get())
        except ValueError:
            messagebox.showerror('Invalid time', 'Enter a numeric time t in seconds (e.g. 8.0).')
            return
        default_dir = KV.CACHE_DIR
        os.makedirs(default_dir, exist_ok=True)
        out_path = filedialog.asksaveasfilename(
            title='Save PNG composite',
            initialdir=default_dir,
            initialfile=f'{c["id"]}_t{t_val:.1f}s.png',
            defaultextension='.png',
            filetypes=[('PNG image', '*.png')],
        )
        if not out_path:
            return
        cmd = worker_cmd('--worker-render', c['id'], '--out', out_path, '--t', str(t_val), *self._option_flags())
        log_msg(f'Rendering PNG: {cmd}')
        self.status_var.set(f'Rendering PNG for {c["id"]} at t={t_val:.2f} s...')
        self.btn_png.configure(state='disabled')

        def _work():
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or f'Exit code {proc.returncode}').strip()
                    log_msg(f'PNG render error: {err}')
                    self.root.after(0, lambda: self._show_error('Save PNG failed', err))
                else:
                    log_msg(f'Saved PNG: {out_path}')
                    self.root.after(0, lambda: (
                        self.status_var.set(f'Saved PNG: {out_path}'),
                        messagebox.showinfo('PNG saved', f'Saved composite PNG:\n{out_path}'),
                    ))
            except Exception as exc:
                log_msg(f'PNG render exception: {traceback.format_exc()}')
                self.root.after(0, lambda: self._show_error('Save PNG failed', str(exc)))
            finally:
                self.root.after(0, lambda: self.btn_png.configure(state='normal'))

        threading.Thread(target=_work, daemon=True).start()

    def on_render_blender(self):
        c = self._selected_entry()
        if c is None:
            return
        if not self.blender_exe or not self.blender_script:
            messagebox.showerror('Blender not found', 'Install Blender 5.2 to render studio clips.')
            return
        try:
            t0 = float(self.bl_t0_var.get())
            length = float(self.bl_len_var.get())
            if length <= 0:
                raise ValueError('Length must be > 0')
        except ValueError as exc:
            messagebox.showerror('Invalid clip range', f'Check Start / Length values: {exc}')
            return

        stamp = datetime.datetime.now().strftime('%H%M%S')
        out_dir = os.path.join(KV.CACHE_DIR, f'blender_{c["id"]}_{stamp}')
        json_path = os.path.join(KV.CACHE_DIR, f'blender_{c["id"]}_{stamp}.json')
        os.makedirs(out_dir, exist_ok=True)
        self.btn_blender.configure(state='disabled')
        self.status_var.set(f'Exporting + rendering Blender clip for {c["id"]} ({t0:.1f}..{t0 + length:.1f} s)...')
        log_msg(f'Blender clip start: {c["id"]} t0={t0} len={length} -> {out_dir}')

        def _work():
            try:
                cmd_exp = worker_cmd(
                    '--worker-export', c['id'], '--out', json_path,
                    '--t0', str(t0), '--length', str(length), '--fps', '25',
                )
                p1 = subprocess.run(cmd_exp, capture_output=True, text=True)
                if p1.returncode != 0:
                    raise RuntimeError(f'Export failed:\n{(p1.stderr or p1.stdout).strip()}')
                cmd_bl = [
                    self.blender_exe, '-b', '-P', self.blender_script, '--',
                    json_path, out_dir, '--samples', '16',
                ]
                p2 = subprocess.run(cmd_bl, capture_output=True, text=True)
                if p2.returncode != 0:
                    raise RuntimeError(f'Blender render failed:\n{(p2.stderr or p2.stdout).strip()}')
                log_msg(f'Blender clip finished -> {out_dir}')
                self.root.after(0, lambda: self.status_var.set(f'Blender clip done -> {out_dir}'))
                if os.name == 'nt':
                    os.startfile(out_dir)
            except Exception as exc:
                log_msg(f'Blender clip error: {traceback.format_exc()}')
                self.root.after(0, lambda: self._show_error('Blender render failed', str(exc)))
            finally:
                self.root.after(0, lambda: self.btn_blender.configure(state='normal'))

        threading.Thread(target=_work, daemon=True).start()

    def _show_error(self, title, msg):
        self.status_var.set(f'Error: {title} (see {LOG_PATH})')
        messagebox.showerror(title, f'{msg[:900]}\n\nFull log: {LOG_PATH}')


def _capture_tk_window(root, out_png):
    """Capture the picker Tk window to PNG via Win32 PrintWindow (works even if desktop is locked)."""
    import ctypes
    from PIL import Image

    root.update_idletasks()
    root.update()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()

    class RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32), ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16), ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32), ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32), ('biClrImportant', ctypes.c_uint32),
        ]

    rc = RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rc))
    w = max(1, rc.right - rc.left)
    h = max(1, rc.bottom - rc.top)

    hdc_win = ctypes.windll.user32.GetWindowDC(hwnd)
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_win)
    hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
    # PW_RENDERFULLCONTENT = 2
    ctypes.windll.user32.PrintWindow(hwnd, hdc_mem, 2)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0  # BI_RGB

    buf = ctypes.create_string_buffer(w * h * 4)
    ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(hwnd, hdc_win)

    img = Image.frombuffer('RGB', (w, h), buf, 'raw', 'BGRX', 0, 1)
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    img.save(out_png)
    log_msg(f'Captured picker screenshot ({w}x{h}) -> {out_png}')


def _run_smoke_test(out_dir):
    """Automated check: verify catalog, open 3 motions' MuJoCo models, and save 1 PNG via --worker-render."""
    t0 = time.perf_counter()
    os.makedirs(out_dir, exist_ok=True)
    cat = KV.build_catalog()
    n_avail = sum(1 for c in cat if c.get('available', True))
    print(f'Catalog: {len(cat)} motions ({n_avail} available)', flush=True)
    test_ids = ['walk_healthy', 'sit_to_stand', 'stairs_up']
    for mid in test_ids:
        e = KV.resolve_motion_id(mid, cat)
        d = KV.load_motion(e)
        m = KV.add_camera_to_model(d['meta'])
        print(f'  Opened {mid} -> {e["id"]}: {len(d["t"])} samples, ngeom={m.ngeom}, nmesh={m.nmesh}', flush=True)
    png_out = os.path.join(out_dir, 'exe_smoke_walk_healthy.png')
    proc = subprocess.run(
        worker_cmd('--worker-render', 'walk_healthy', '--out', png_out, '--t', '10.0'),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'worker-render failed: {proc.stderr or proc.stdout}')
    dt = time.perf_counter() - t0
    print(f'Saved PNG: {png_out} ({os.path.getsize(png_out)} bytes) in {dt:.2f} s total', flush=True)
    return 0


def main():
    print(VERSION, flush=True)
    ap = argparse.ArgumentParser(description='KNEIL 3D Motion Viewer launcher')
    ap.add_argument('--worker-viewer', dest='worker_viewer', action='store_true')
    ap.add_argument('--worker-render', dest='worker_render', action='store_true')
    ap.add_argument('--worker-export', dest='worker_export', action='store_true')
    ap.add_argument('--screenshot', metavar='OUT.png', help='open picker, capture window screenshot, and exit')
    ap.add_argument('--smoke-test', metavar='OUT_DIR', help='headless verification of 3 motions + PNG save')
    ap.add_argument('motion', nargs='?')
    ap.add_argument('--out', default='')
    ap.add_argument('--t', type=float, default=8.0)
    ap.add_argument('--t0', type=float, default=4.0)
    ap.add_argument('--length', type=float, default=2.0)
    ap.add_argument('--fps', type=float, default=25.0)
    ap.add_argument('--speed', type=float, default=1.0)
    ap.add_argument('--no-cad', action='store_true')
    ap.add_argument('--no-see-through', action='store_true')
    args = ap.parse_args()

    try:
        if args.worker_viewer:
            return _run_worker_viewer(args)
        if args.worker_render:
            return _run_worker_render(args)
        if args.worker_export:
            return _run_worker_export(args)
        if args.smoke_test:
            return _run_smoke_test(args.smoke_test)

        t_start = time.perf_counter()
        log_msg(f'Starting {VERSION} (frozen={getattr(sys, "frozen", False)})')
        catalog = KV.build_catalog()
        root = tk.Tk()
        app = MotionPickerApp(root, catalog)
        dt = time.perf_counter() - t_start
        log_msg(f'Picker window ready in {dt:.2f} s ({len(catalog)} motions)')
        if args.screenshot:
            root.after(700, lambda: (_capture_tk_window(root, args.screenshot), root.destroy()))
        root.mainloop()
        return 0
    except Exception as exc:
        tb = traceback.format_exc()
        log_msg(f'Fatal error: {tb}')
        is_headless = bool(args.worker_render or args.worker_export or args.smoke_test or args.screenshot)
        if not is_headless:
            try:
                r = tk.Tk()
                r.withdraw()
                messagebox.showerror('KNEIL Viewer Error', f'{exc}\n\nFull log: {LOG_PATH}')
                r.destroy()
            except Exception:
                pass
        else:
            sys.stderr.write(tb + '\n')
        return 1


if __name__ == '__main__':
    sys.exit(main())
