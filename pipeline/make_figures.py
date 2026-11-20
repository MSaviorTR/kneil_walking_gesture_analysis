#!/usr/bin/env python
"""
KNEIL V4 figures for talks, meetings and the thesis draft.   make_figures 1.1, 20 Nov 2026

Reads the step D result files and the E2 build report and writes the figures as PNG (300 dpi) and SVG to
docs/figures/ (the overview also as PDF).  Nothing is trained and no window is rebuilt: the script only reads
cached files.

Sources of the numbers (printed per panel, also in docs/figures/make_figures_log.txt):
  KNEIL_results/v4/stepD/D3/stairs_rule_results.csv        (A4 and the overview: published before/after tables)
  KNEIL_results/v4/stepD/D3/transition_events_results.csv  (A4: event recall, false events)
  KNEIL_results/v4/stepD/D2/pred_*_W*s_8cls_seed*.npz      (A1-A3, A5 and the overview: per-window predictions)
  KNEIL_results/v4/stepD/windows_v11/windows_W{2,4}s.npz   (truth, stream ids, dataset, people)
  tasks/E2_report.md                                       (B2 and the overview: measured flash / RAM)
  ../kneil_firmware/protocol/kneil_proto.h                 (B3: packet sizes)
  ../kneil_firmware/pc_app/kneil/protocol.py               (class names and colours)

Run: python pipeline/make_figures.py                 (all figures, about 10 s)
     python pipeline/make_figures.py --only overview  (just the overview)
"""
import argparse
import os
import re
import sys
import time
import datetime
import textwrap

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.text as mtext
from matplotlib.colors import LinearSegmentedColormap, to_hex
from matplotlib.patches import FancyBboxPatch, Patch, Circle

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config
import cv_v4 as C
import stairs_rule as SR

VERSION = 'make_figures 1.1'
OUT = os.path.join(config.WORKSPACE, 'docs', 'figures')
LOG_PATH = os.path.join(OUT, 'make_figures_log.txt')
SEEDS = (0, 1, 2)
STEPD = os.path.join(config.V4_OUT, 'stepD')
FW = os.path.normpath(os.path.join(config.WORKSPACE, '..', 'kneil_firmware'))

# ---- one palette for the whole set -----------------------------------------
C_TODAY = '#9e9e9e'          # today / V3, always grey
C_V4 = '#0072b2'             # V4, always this accent
C_V4_NORULE = '#7fb8dd'      # V4 without the rule: same hue, lighter
C_INK = '#222222'
C_RULE = '#555555'
C_BAD = '#b2182b'

_LOG = []


def log(msg):
    msg = str(msg)
    try:
        print(msg)
    except UnicodeEncodeError:          # Windows console in cp1252: keep the run going, the file log is UTF-8
        print(msg.encode("ascii", "replace").decode("ascii"))
    _LOG.append(msg)


def save(fig, name, pdf=False, svg_paths=False):
    # PNG and SVG; the SVG gets no date and a fixed hash salt so re-runs do not change it
    fig.savefig(os.path.join(OUT, name + '.png'), dpi=300, bbox_inches='tight', facecolor='white')
    md = {'Date': None}
    if svg_paths:          # text as outlines: identical in PowerPoint/Inkscape without the fonts
        with matplotlib.rc_context({'svg.fonttype': 'path'}):
            fig.savefig(os.path.join(OUT, name + '.svg'), bbox_inches='tight', facecolor='white', metadata=md)
    else:
        fig.savefig(os.path.join(OUT, name + '.svg'), bbox_inches='tight', facecolor='white', metadata=md)
    if pdf:                # vector, TrueType embedded (pdf.fonttype = 42 in style())
        fig.savefig(os.path.join(OUT, name + '.pdf'), facecolor='white')
    plt.close(fig)
    log(f'  wrote {name}.png, {name}.svg' + (f' and {name}.pdf' if pdf else ''))


def style():
    plt.rcParams.update({
        'font.size': 11, 'axes.titlesize': 13, 'axes.labelsize': 11,
        'xtick.labelsize': 11, 'ytick.labelsize': 11, 'legend.fontsize': 10.5,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.edgecolor': '#666666', 'axes.labelcolor': C_INK, 'text.color': C_INK,
        'xtick.color': C_INK, 'ytick.color': C_INK,
        'axes.grid': True, 'grid.color': '#e6e6e6', 'grid.linewidth': 0.8,
        'figure.facecolor': 'white', 'svg.fonttype': 'none', 'svg.hashsalt': 'kneil-figures',
        'pdf.fonttype': 42,
    })


# ---- constants read from files ---------------------------------------------
def protocol_colours():
    """The 8-class v2 names and colours, read from the PC app's protocol.py."""
    path = os.path.join(FW, 'pc_app', 'kneil', 'protocol.py')
    text = open(path, encoding='utf-8').read()

    def tup(name):
        m = re.search(name + r'\s*=\s*\(([^)]*)\)', text, re.S)
        if not m:
            raise SystemExit(f'{path}: {name} not found')
        return [s.strip().strip("'\"") for s in m.group(1).replace('\n', ' ').split(',') if s.strip()]

    labels, cols = tup('CLASS_LABELS_V2'), tup('CLASS_COLOURS_V2')
    if len(labels) != 8 or len(cols) != 8:
        raise SystemExit(f'{path}: expected 8 class names and colours, found {len(labels)} / {len(cols)}')
    log(f'[style] class names/colours: {os.path.relpath(path, config.WORKSPACE)} (CLASS_LABELS_V2, CLASS_COLOURS_V2)')
    return labels, cols


def protocol_sizes():
    """Packet sizes, read from the KNEIL protocol header."""
    path = os.path.join(FW, 'protocol', 'kneil_proto.h')
    text = open(path, encoding='utf-8').read()

    def num(name):
        m = re.search(r'#define\s+' + name + r'\s+(\d+)', text)
        if not m:
            raise SystemExit(f'{path}: {name} not found')
        return int(m.group(1))

    sizes = {'live': num('KNEIL_LIVE_V2_LEN'), 'summary': num('KNEIL_SUMMARY_LEN'),
             'raw_hdr': num('KNEIL_RAW_HDR_LEN'), 'raw_n': num('KNEIL_RAW_N_NORMAL')}
    log(f'[style] packet sizes: {os.path.relpath(path, config.WORKSPACE)} '
        f'LIVE_V2_LEN={sizes["live"]} SUMMARY_LEN={sizes["summary"]} RAW_HDR_LEN={sizes["raw_hdr"]} '
        f'RAW_N_NORMAL={sizes["raw_n"]}')
    return sizes


def e2_sizes():
    """Measured build sizes from the E2 report (the script stops if a pattern is gone)."""
    path = os.path.join(config.WORKSPACE, 'tasks', 'E2_report.md')
    text = open(path, encoding='utf-8').read()

    def num(pat, what):
        m = re.search(pat, text)
        if not m:
            raise SystemExit(f'{path}: cannot read {what}')
        return int(m.group(1).replace(',', '').replace(' ', ''))

    sizes = {
        'forest_bytes': num(r'V4 forest ([\d,]+) B', 'the V4 forest symbol size'),
        'fw_flash': num(r'KNEIL live, forest \(V4\) \| \*\*([\d,]+) B\*\*', 'firmware flash'),
        'fw_ram': num(r'KNEIL live, forest \(V4\) \|.*?\| \*\*([\d,]+) B\*\*', 'firmware RAM'),
        'classifier': num(r'classifier ([\d,]+) B', 'classifier RAM'),
        'metrics': num(r'metrics ([\d,]+) B', 'daily-metrics RAM'),
        'summary': num(r'summary ([\d,]+) B', 'summary bytes'),
    }
    log(f'[style] build sizes: {os.path.relpath(path, config.WORKSPACE)} forest={sizes["forest_bytes"]} B, '
        f'flash={sizes["fw_flash"]} B, RAM={sizes["fw_ram"]} B, classifier={sizes["classifier"]} B, '
        f'metrics={sizes["metrics"]} B, summary={sizes["summary"]} B')
    return sizes


# ---- step D data -----------------------------------------------------------
_WINDOWS = {}
_CACHE = {}


def windows(win):
    if win not in _WINDOWS:
        A = C.load(win)
        _WINDOWS[win] = (A, C.y_for(A, 8))
    return _WINDOWS[win]


def pred_path(variant, win, seed):
    return os.path.join(STEPD, 'D2', f'pred_{variant}_W{win}s_8cls_seed{seed}.npz')


def rule_tables(win, variant, theta):
    """pipeline/stairs_rule.metrics for one variant/window, per seed, with or without the stairs rule."""
    key = (win, variant, theta)
    if key in _CACHE:
        return _CACHE[key]

    A, y = windows(win)
    stage = 'before' if theta is None else 'after_06'
    frames = []

    for seed in SEEDS:
        z = np.load(pred_path(variant, win, seed))
        pred, proba = z['pred'], z['proba']
        if theta is not None:
            pa = SR.proba_at(pred, proba)
            roll = SR.rolling_stair_counts(pred, A['stream'])
            pred = SR.apply_rule(pred, pa, roll, theta, 1, 1)
        rows = SR.metrics(A, y, pred, stage, variant, win, seed)

        # stairs_rule.metrics walks only the real datasets; add the simulated walking recall
        ok = pred >= 0
        m = ok & (A['src'] == 'sim') & (y == 0)
        rows.append(dict(variant=variant, win=win, seed=seed, stage=stage, table='walking', dataset='simulated',
                         key='walking', metric='recall_pct', value=100.0 * float((pred[m] == 0).mean()),
                         n=int(m.sum())))
        frames.append(pd.DataFrame(rows))

    D = pd.concat(frames, ignore_index=True)
    _CACHE[key] = D
    return D


def agg(D):
    return (D.groupby(['variant', 'win', 'stage', 'table', 'dataset', 'key', 'metric'], dropna=False)
            .agg(value=('value', 'mean'), sd=('value', 'std'), n=('n', 'first')).reset_index())


def make_lookup(G_before, G_after):
    """lookup(variant, win, stage, ...) -> (mean, sd, n) from the aggregated tables."""
    def lookup(variant, win, stage, table, dataset, key, metric):
        D = G_after if stage == 'after_06' else G_before[(variant, win)]
        s = D[(D.variant == variant) & (D.win == win) & (D.stage == stage) & (D.table == table) &
              (D.dataset == dataset) & (D.key == key) & (D.metric == metric)]
        if len(s) != 1:
            raise SystemExit(f'no single row for {variant} {win}s {stage} {table} {dataset} {key} {metric}: '
                             f'{len(s)}')
        sd = float(s.sd.iloc[0])
        return float(s.value.iloc[0]), (sd if np.isfinite(sd) else 0.0), int(s.n.iloc[0])
    return lookup


def people_counts(A):
    """People per dataset = distinct groups in the window file; 'simulated' counts personas (src == sim)."""
    u = pd.DataFrame({'ds': A['ds'], 'grp': A['grp'], 'src': A['src']}).drop_duplicates()
    out = u.groupby('ds').size().to_dict()
    out['simulated'] = int(len(u[u.src == 'sim']))
    return out


# ---- figure A1 -------------------------------------------------------------
def fig_a1(lookup):
    cats = [('Lencioni', 'speed_abs=fast', 'Lencioni\nfast walkers (50)'),
            ('Luo', 'surface=FE', 'Luo\nlevel walking (30)'),
            ('WearGait-PD', 'rec=HurriedPace', 'WearGait-PD\nHurriedPace (109)')]
    series = [('today (V3recipe 2 s)', 'V3recipe', 2, 'before', C_TODAY),
              ('V4half 4 s', 'V4half', 4, 'before', C_V4_NORULE),
              ('V4half 4 s + rule 0.6', 'V4half', 4, 'after_06', C_V4)]

    log('[A1] sources: stepD/D3/stairs_rule_results.csv (today / no rule) and stepD/D2/pred_V4half_W4s_8cls_seed*.npz + '
        'stepD/windows_v11/windows_W4s.npz (rule vote >= 0.6)')
    fig, ax = plt.subplots(figsize=(10, 5.6))
    w = 0.26
    x = np.arange(len(cats))
    for k, (label, variant, win, stage, col) in enumerate(series):
        vals, errs = [], []
        for ds, key, _ in cats:
            v, s, n = lookup(variant, win, stage, 'called', ds, key, 'walking_called_stairs_pct')
            vals.append(v); errs.append(s)
            log(f'   {label} | {ds} {key}: {v:.2f} % (sd {s:.2f} over 3 seeds, n {n})')
        ax.bar(x + (k - 1) * w, vals, w, yerr=errs, capsize=4, color=col, edgecolor='white',
               error_kw=dict(ecolor=C_RULE, lw=1.2), label=label)
        for xi, v in zip(x + (k - 1) * w, vals):
            ax.text(xi, v + 0.5, f'{v:.1f}', ha='center', va='bottom', fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([c[2] for c in cats])
    ax.set_ylabel('% of true walking windows called stairs')
    ax.set_ylim(0, 21)
    fig.suptitle('A1  Fast walking misread as stairs', fontsize=13, y=0.98)
    fig.text(0.5, 0.925, 'mean of 3 seeds, CV by person; lower is better', ha='center', fontsize=10.5, color=C_RULE)
    ax.legend(frameon=False, loc='upper right')
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    save(fig, 'A1_walking_called_stairs')


# ---- figure A2 -------------------------------------------------------------
def fig_a2(lookup, people):
    real = ['WearGait-PD', 'Lencioni', 'Luo', 'KneE-PAD', 'MHEALTH', 'PAMAP2', 'Marpino', 'CeTI']
    rows = sorted(real, key=lambda d: -people.get(d, 0)) + ['simulated']
    labels = []
    for d in rows:
        n = people.get(d, 0)
        if d == 'simulated':
            labels.append('simulated*')
        else:
            labels.append(f'{d} ({n} people)' + ('†' if n < 10 else ''))
    series = [('today (V3recipe 2 s)', 'V3recipe', 2, 'before', C_TODAY),
              ('V4half 4 s', 'V4half', 4, 'before', C_V4_NORULE),
              ('V4half 4 s + rule 0.6', 'V4half', 4, 'after_06', C_V4)]

    log('[A2] sources: stepD/D2/pred_*_W*s_8cls_seed*.npz + windows_v11/windows_W{2,4}s.npz (walking recall, rule 0.6 '
        'for the last series); people = distinct grp in windows_W4s.npz')
    fig, ax = plt.subplots(figsize=(10, 5.6))
    h = 0.26
    y = np.arange(len(rows))
    for k, (name, variant, win, stage, col) in enumerate(series):
        vals, errs = [], []
        for d in rows:
            v, s, n = lookup(variant, win, stage, 'walking', d, 'walking', 'recall_pct')
            vals.append(v); errs.append(s)
            log(f'   {name} | {d}: {v:.1f} % (sd {s:.1f}, n {n} windows)')
        ax.barh(y - (k - 1) * h, vals, h, xerr=errs, capsize=3, color=col, edgecolor='white',
                error_kw=dict(ecolor=C_RULE, lw=1.0), label=name)
        for yi, v in zip(y - (k - 1) * h, vals):
            ax.text(v - 2.0, yi, f'{v:.0f}', va='center', ha='right', fontsize=9.5,
                    color='white' if col == C_V4 else C_INK)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    for t, d in zip(ax.get_yticklabels(), rows):
        if d == 'simulated':
            t.set_style('italic')
        elif people.get(d, 0) < 10:
            t.set_color(C_BAD)
    ax.set_xlim(0, 106)
    ax.set_xlabel('walking recall (%)')
    fig.suptitle('A2  Walking recognised per dataset', fontsize=13, y=0.98)
    fig.text(0.5, 0.925, 'mean of 3 seeds, CV by person; † fewer than 10 people; '
                         f'*simulated ({people["v1.6 synthetic"]} synthetic personas + Camargo replay, '
                         f'{people["Camargo simulated"]} people)',
             ha='center', fontsize=10, color=C_RULE)
    fig.legend(*ax.get_legend_handles_labels(), ncol=3, frameon=False, loc='lower center',
               bbox_to_anchor=(0.5, 0.005))
    fig.tight_layout(rect=(0, 0.06, 1, 0.91))
    save(fig, 'A2_walking_per_dataset')


# ---- figure A3 -------------------------------------------------------------
def fig_a3(lookup):
    cfg = [('today\n(V3recipe 2 s)', 'V3recipe', 2, 'before', C_TODAY),
           ('V4half 4 s', 'V4half', 4, 'before', C_V4_NORULE),
           ('V4half 4 s\n+ rule 0.6', 'V4half', 4, 'after_06', C_V4)]
    panels = [('Luo (30 people)', 'Luo'), ('PAMAP2 (7 people)†', 'PAMAP2')]

    log('[A3] sources: stepD/D3/stairs_rule_results.csv (today / no rule) and stepD/D2/pred_V4half_W4s_8cls_seed*.npz + '
        'stepD/windows_v11/windows_W4s.npz (rule vote >= 0.6)')
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.6), sharey=True)
    w = 0.2
    for ax, (title, ds) in zip(axes, panels):
        x = np.arange(len(cfg))
        for j, (cls, col, hatch) in enumerate([('stairs_up', '#ff9a1f', ''), ('stairs_up', '#ff9a1f', '///'),
                                               ('stairs_down', '#c65102', ''), ('stairs_down', '#c65102', '///')]):
            metric = 'recall_pct' if hatch == '' else 'precision_pct'
            vals, errs = [], []
            for label, variant, win, stage, _ in cfg:
                v, s, n = lookup(variant, win, stage, 'stairs', ds, cls, metric)
                vals.append(v); errs.append(s)
                log(f'   {ds} {cls} {metric} | {label.replace(chr(10), " ")}: {v:.1f} % (sd {s:.1f}, n {n})')
            ax.bar(x + (j - 1.5) * w, vals, w, yerr=errs, capsize=2.5, color=col, edgecolor='white',
                   hatch=hatch, error_kw=dict(ecolor=C_RULE, lw=1.0))
            for xi, v in zip(x + (j - 1.5) * w, vals):
                ax.text(xi, v + 1.5, f'{v:.0f}', ha='center', va='bottom', fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels([c[0] for c in cfg])
        ax.set_title(title, fontsize=12)
        ax.set_ylim(0, 106)
        ax.grid(axis='x', visible=False)
    axes[0].set_ylabel('percent')
    fig.suptitle('A3  Stairs: recall (filled) and precision (hatched), mean of 3 seeds, CV by person', fontsize=12.5)
    handles = [Patch(facecolor='#ff9a1f', label='stairs up'), Patch(facecolor='#c65102', label='stairs down'),
               Patch(facecolor='white', edgecolor='#666666', label='recall'),
               Patch(facecolor='white', edgecolor='#666666', hatch='///', label='precision')]
    fig.legend(handles=handles, ncol=4, frameon=False, loc='lower center', bbox_to_anchor=(0.5, 0.005))
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    save(fig, 'A3_stairs_recall_precision')


# ---- figure A4 -------------------------------------------------------------
def fig_a4():
    rule = pd.read_csv(os.path.join(STEPD, 'D3', 'stairs_rule_results.csv'))
    events = pd.read_csv(os.path.join(STEPD, 'D3', 'transition_events_results.csv'))

    def pick(df, **kw):
        s = df.copy()
        for k, v in kw.items():
            s = s[s[k] == v]
        return s.sort_values('win')

    f05 = pick(rule, variant='V4half', stage='after_f05', table='merged', dataset='Luo', key='stairs',
               metric='f05_pct')
    ev = pick(events, variant='V4half', rule='R1', table='events', source='simulation', metric='event_recall_pct')
    fl = events[events.table == 'false']
    fl = (fl[(fl.variant == 'V4half') & (fl.rule == 'R1')]
          .groupby('win', as_index=False).agg(value=('value', 'max')))

    log('[A4] sources: stepD/D3/stairs_rule_results.csv (F0.5, V4half, after_f05) and '
        'stepD/D3/transition_events_results.csv (events: simulation, rule R1; false: worst source per window)')
    for name, d in (('Luo stairs F0.5', f05), ('STS event recall (simulated)', ev), ('false events/h (worst)', fl)):
        log(f'   {name}: ' + ', '.join(f'{w:g}s={v:.2f}' for w, v in zip(d.win, d.value)))

    fig, axes = plt.subplots(3, 1, figsize=(10, 6.0), sharex=True)
    specs = [(axes[0], f05, 'Luo stairs F0.5 (%)', 'higher is better'),
             (axes[1], ev, 'STS event recall, simulated (%)', 'higher is better'),
             (axes[2], fl, 'false events per hour', 'lower is better')]
    for ax, d, ptitle, note in specs:
        ax.plot(d.win, d.value, '-o', color=C_V4, lw=2, ms=6)
        for w, v in zip(d.win, d.value):
            ax.annotate(f'{v:.1f}', (w, v), textcoords='offset points', xytext=(9 if w == 4 else 0, 11),
                        ha='center', fontsize=10)
        ax.axvline(4, color=C_RULE, ls='--', lw=1)
        ax.set_title(ptitle, loc='left', fontsize=11)
        ax.text(0.995, 0.06, note, transform=ax.transAxes, ha='right', fontsize=9.5, color=C_RULE)
        ax.grid(axis='x', visible=False)
        ax.margins(x=0.08, y=0.30)
    axes[2].set_xlabel('window length (s)')
    axes[2].set_xticks([2, 3, 4, 5])
    axes[0].text(4.06, axes[0].get_ylim()[1], 'chosen: 4 s', fontsize=10.5, color=C_RULE, va='top')
    fig.suptitle('A4  Window-length trade-off (V4half; mean of 3 seeds, CV by person)', fontsize=12.5, y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, 'A4_window_length_tradeoff')


# ---- figure A5 -------------------------------------------------------------
def confusion(win, variant, theta):
    A, y = windows(win)
    real = A['src'] == 'real'
    out = {'real': [], 'simulated': []}
    for seed in SEEDS:
        z = np.load(pred_path(variant, win, seed))
        pred, proba = z['pred'], z['proba']
        pa = SR.proba_at(pred, proba)
        roll = SR.rolling_stair_counts(pred, A['stream'])
        pred = SR.apply_rule(pred, pa, roll, theta, 1, 1)
        for name, mask in (('real', real), ('simulated', ~real)):
            m = mask & (pred >= 0) & (y >= 0)
            cm = np.zeros((8, 8), np.float64)
            np.add.at(cm, (y[m], pred[m]), 1.0)
            out[name].append(cm)
    return {k: np.mean(v, axis=0) for k, v in out.items()}


def fig_a5(cms, labels, cols):
    log('[A5] sources: stepD/D2/pred_V4half_W4s_8cls_seed*.npz (mean over seeds) + windows_v11/windows_W4s.npz '
        '(truth, src); rule = vote >= 0.6, k=1, n=1 (pipeline/stairs_rule.py)')
    short = ['walk', 'stairs\nup', 'stairs\ndown', 'still', 'lying', 'sit-to\nstand', 'stand-to\nsit', 'bed\ntransfer']
    cmap = LinearSegmentedColormap.from_list('kneil_blue', ['#ffffff', '#cfe3f2', C_V4])
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.6))
    for ax, (name, title) in zip(axes, (('real', 'real data only'), ('simulated', 'simulated only'))):
        cm = cms[name]
        n = cm.sum(axis=1)
        pct = np.divide(cm, n[:, None], out=np.zeros_like(cm), where=n[:, None] > 0) * 100.0
        ax.imshow(pct, cmap=cmap, vmin=0, vmax=100)
        for i in range(8):
            for j in range(8):
                if n[i] <= 0:
                    continue
                v = pct[i, j]
                if v >= 0.5:
                    ax.text(j, i, f'{v:.0f}', ha='center', va='center', fontsize=8.5,
                            color='white' if v > 55 else C_INK)
        ax.set_xticks(range(8))
        ax.set_yticks(range(8))
        ax.set_xticklabels(short, fontsize=8.5)
        ax.set_yticklabels([f'{s}  ({int(v):,})' for s, v in zip(short, n)], fontsize=8.5)
        for t, c in zip(ax.get_yticklabels(), cols):
            t.set_color(c)
        ax.set_xlabel('predicted')
        ax.set_title(title, fontsize=12)
        ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(True)
            s.set_color('#999999')
        log(f'   {name}: windows per row ' + ', '.join(f'{l}={int(v)}' for l, v in zip(labels, n)))
        log(f'   {name}: diagonal ' + ', '.join(f'{l}={pct[i, i]:.1f}%' for i, l in enumerate(labels)))
    fig.suptitle('A5  Confusion matrix, V4half 4 s + stairs rule 0.6, row-normalised % '
                 '(mean of 3 seeds, CV by person)', fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save(fig, 'A5_confusion_matrix')


# ---- figure B1 -------------------------------------------------------------
def axes_height_in(ax):
    """Height of the axes in inches (the y axis runs 0..1 over it)."""
    return ax.figure.get_size_inches()[1] * ax.get_position().height


def box(ax, x, y, w, h, title, body='', ts=11.5, bs=10.0, wrap_b=22, wrap_t=17):
    fig_h = axes_height_in(ax)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.006,rounding_size=0.012',
                                linewidth=1.2, edgecolor='#555555', facecolor='#ffffff'))
    t = textwrap.fill(title, wrap_t) if wrap_t else title
    if body:
        b = '\n'.join(textwrap.fill(line, wrap_b) if line.strip() else '' for line in body.split('\n'))
        lh = bs * 1.45 / 72.0 / fig_h          # line height in axes units
        th = ts * 1.25 / 72.0 / fig_h
        n_t = t.count('\n') + 1
        top = y + h - 0.012
        ax.text(x + w / 2, top, t, ha='center', va='top', fontsize=ts, fontweight='bold', color=C_INK)
        ax.text(x + w / 2, top - n_t * th - 0.012, b, ha='center', va='top', fontsize=bs,
                color=C_INK, linespacing=1.45)
    else:
        ax.text(x + w / 2, y + h / 2, t, ha='center', va='center', fontsize=ts, fontweight='bold', color=C_INK)


def arrow(ax, x0, y0, x1, y1):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='-|>', lw=1.5, color='#555555', shrinkA=0, shrinkB=0))


def measure(ax, title, body, ts, bs, wrap_t=17, wrap_b=22):
    """Height of a box that holds exactly this wrapped text (plus a small margin)."""
    fig_h = axes_height_in(ax)
    t = textwrap.fill(title, wrap_t) if wrap_t else title
    b = '\n'.join(textwrap.fill(line, wrap_b) if line.strip() else '' for line in body.split('\n')) if body else ''
    th = ts * 1.25 / 72.0 / fig_h
    lh = bs * 1.45 / 72.0 / fig_h
    n_b = (b.count('\n') + 1) if b else 0
    return 0.024 + (t.count('\n') + 1) * th + ((0.012 + n_b * lh) if n_b else 0.0)


def fig_b1(people):
    src = (f'shank IMUs\nWearGait-PD {people["WearGait-PD"]}\n'
           f'Luo {people["Luo"]}, KneE-PAD {people["KneE-PAD"]}\n'
           f'PAMAP2 {people["PAMAP2"]}, MHEALTH {people["MHEALTH"]}\n'
           f'Marpino {people["Marpino"]}\n\n'
           f'motion suits\nCeTI {people["CeTI"]}\n\n'
           f'markers\nLencioni {people["Lencioni"]}\nCaicedo {people["Caicedo older adults"]}\n\n'
           f'simulation\n{people["v1.6 synthetic"]} personas\n'
           f'+ Camargo replay ({people["Camargo simulated"]})')
    log('[B1] people counts: stepD/windows_v11/windows_W4s.npz (distinct groups per dataset); pipeline steps from '
        'CLAUDE.md / docs/STEP_D_SUMMARY.md / README.md')
    log('   people: ' + ', '.join(f'{k}={v}' for k, v in sorted(people.items())))

    fig, ax = plt.subplots(figsize=(12, 6.75))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    w = 0.175
    xs = [0.010, 0.212, 0.414, 0.616, 0.818]
    specs = [
        ('Public gait data', src),
        ('Virtual implant',
         'rigid-body transfer\nf_P = f_S + a×r + w×(w×r)\n\none tibia frame\nper person\n(z gravity,\ny rotation axis)'
         '\n\nplausibility rule:\nforward lean -5…+35°'),
        ('Implant signals', '3-axis accelerometer\n50 Hz, ±8 g\n\ncausal 6 Hz low-pass\n\n4 s windows, 1 s hop\n'
                            '(same for every dataset)'),
        ('Model', '20 features per window\n(same C code as the chip)\n\nrandom forest\n20 trees × depth 10\n\n'
                  '5-fold CV by person\n3 seeds'),
        ('Export', 'emlearn\n\nkneil_tinyml v2.0\n\n8 classes\n(4 s window, 1 s hop)\n\n'
                   'V4half: new data\nat half weight')]
    hs = [measure(ax, t, b, 12, 10.5, 19, 21) for t, b in specs]
    H = max(hs)
    y_top = 0.92
    for i, ((t, b), h) in enumerate(zip(specs, hs)):
        box(ax, xs[i], y_top - h, w, h, t, b, ts=12, bs=10.5, wrap_b=21, wrap_t=19)
        if i:
            arrow(ax, xs[i - 1] + w + 0.004, y_top - H / 2, xs[i] - 0.004, y_top - H / 2)
    ax.set_title('B1  Training data pipeline: from public gait data to the chip library', fontsize=13)
    ax.text(0.5, 0.03, 'people counts from the window file (W4); the simulation mixes synthetic personas and the '
                       'Camargo replay', ha='center', fontsize=10, color=C_RULE)
    save(fig, 'B1_training_pipeline')


# ---- figure B2 -------------------------------------------------------------
def fig_b2(sz, proto):
    log('[B2] sizes: tasks/E2_report.md (forest '
        f'{sz["forest_bytes"]} B, firmware {sz["fw_flash"]} B flash / {sz["fw_ram"]} B RAM, classifier '
        f'{sz["classifier"]} B, metrics {sz["metrics"]} B, summary {sz["summary"]} B); packet sizes '
        '../kneil_firmware/protocol/kneil_proto.h')
    fig, ax = plt.subplots(figsize=(12, 6.75))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # device row
    w = 0.145
    xs = [0.012 + i * 0.163 for i in range(6)]
    dev = [('Accel. sensor', '50 Hz, ±8 g\n3 axes'),
           ('Low-pass', 'causal 6 Hz\non the device'),
           ('Window', '4 s, 1 s hop\n200 samples/axis'),
           ('Features', '20 per window\nsame C code'),
           ('Forest', f'20 × depth 10\n{sz["forest_bytes"]:,} B flash\n{sz["classifier"]:,} B RAM'),
           ('Rule + events', 'stairs vote ≥ 0.6\nR1 events\nposture state')]
    hs1 = [measure(ax, t, b, 11, 10, 15, 20) for t, b in dev]
    H1 = max(hs1)
    y1_top = 0.95
    for i, ((t, b), h) in enumerate(zip(dev, hs1)):
        box(ax, xs[i], y1_top - h, w, h, t, b, ts=11, bs=10, wrap_b=20, wrap_t=15)
        if i:
            arrow(ax, xs[i - 1] + w + 0.003, y1_top - H1 / 2, xs[i] - 0.003, y1_top - H1 / 2)
    y1 = y1_top - H1

    # daily metrics under the last device box
    dm_x = xs[5]
    dm_t, dm_b = 'Daily metrics', f'posture split, events,\nminutes per class\n{sz["summary"]} B summary'
    Hd = measure(ax, dm_t, dm_b, 11, 10, 15, 20)
    dm_y = y1 - 0.03 - Hd
    box(ax, dm_x, dm_y, w, Hd, dm_t, dm_b, ts=11, bs=10, wrap_b=20, wrap_t=15)
    arrow(ax, dm_x + w / 2, y1 - 0.005, dm_x + w / 2, dm_y + Hd + 0.005)

    # bottom row: BLE -> XIAO -> PC app, and the watch as a second BLE consumer of the implant
    w2 = 0.155
    xs2 = [0.012, 0.190, 0.368]
    x_watch = 0.640
    ble_t, ble_b = 'BLE packets', (f'LIVE {proto["live"]} B/s\nSUMMARY {proto["summary"]} B/min\nINFO (text)\n'
                                   f'RAW {proto["raw_hdr"] + 6 * proto["raw_n"]} B / 0.5 s')
    row = [(ble_t, ble_b), ('XIAO bridge', 'BLE → USB serial\ntext lines'),
           ('PC app', 'live view,\ntruth keys, recording')]
    hs2 = [measure(ax, t, b, 11, 10, 15, 20) for t, b in row]
    H2 = max(hs2)
    y2_top = 0.42
    for i, ((t, b), h) in enumerate(zip(row, hs2)):
        box(ax, xs2[i], y2_top - h, w2, h, t, b, ts=11, bs=10, wrap_b=20, wrap_t=15)
        if i:
            arrow(ax, xs2[i - 1] + w2 + 0.003, y2_top - H2 / 2, xs2[i] - 0.003, y2_top - H2 / 2)
    y2 = y2_top - H2

    watch_t, watch_b = 'Guder watch', 'KNEIL mode:\nlive class, vote,\nposture, events'
    ww = 0.20
    Hw = measure(ax, watch_t, watch_b, 11, 10, 15, 20)
    yw = 0.42 - Hw
    box(ax, x_watch, yw, ww, Hw, watch_t, watch_b, ts=11, bs=10, wrap_b=20, wrap_t=15)

    # daily summary -> BLE packets (data path)
    bus_data = 0.49
    xa = xs2[0] + 0.03
    ax.plot([dm_x + w / 2, dm_x + w / 2], [dm_y - 0.004, bus_data], color='#555555', lw=1.5)
    ax.plot([xa, dm_x + w / 2], [bus_data, bus_data], color='#555555', lw=1.5)
    ax.plot([xa, xa], [bus_data, y2 + H2 + 0.004], color='#555555', lw=1.5)
    arrow(ax, xa, bus_data, xa, y2 + H2 + 0.003)
    # implant -> watch, directly over the bridge and the PC app
    bus_watch = 0.455
    xb = xs2[0] + w2 - 0.03
    ax.plot([xb, xb], [y2 + H2 + 0.004, bus_watch], color='#555555', lw=1.5)
    ax.plot([xb, x_watch + ww / 2], [bus_watch, bus_watch], color='#555555', lw=1.5)
    arrow(ax, x_watch + ww / 2, bus_watch, x_watch + ww / 2, yw + Hw + 0.005)
    ax.text((xs2[2] + w2 + x_watch) / 2, bus_watch + 0.015, 'BLE, direct (central)', ha='center', fontsize=9.5,
            color=C_RULE)

    ax.set_title(f'B2  On the device and after: firmware {sz["fw_flash"]:,} B flash / {sz["fw_ram"]:,} B RAM '
                 '(measured, NCS 3.1.0)', fontsize=12.5)
    save(fig, 'B2_device_and_link')


# ---- figure B3 -------------------------------------------------------------
def fig_b3(sz, proto):
    raw = proto['raw_hdr'] + 6 * proto['raw_n']
    per_day = {'RAW, on request\n(streaming)': raw * 2 * 86400,
               'LIVE, every second\n(normal use)': proto['live'] * 86400,
               'SUMMARY, every minute': proto['summary'] * 1440}
    log('[B3] computed from ../kneil_firmware/protocol/kneil_proto.h: '
        f'RAW {raw} B × 2/s, LIVE {proto["live"]} B × 1/s, SUMMARY {proto["summary"]} B × 1/min, × 86,400 s/day; '
        'payload bytes only, not measured on air')
    for k, v in per_day.items():
        log(f'   {k.splitlines()[0]}: {v:,} B/day = {v / 1e6:.2f} MB/day')

    fig, ax = plt.subplots(figsize=(10, 5.6))
    names, vals = list(per_day), list(per_day.values())
    cols = ['#c65102', C_V4, '#8b5a2b']
    y = np.arange(len(names))
    ax.barh(y, vals, 0.55, color=cols, edgecolor='white')
    ax.set_xscale('log')
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    for yi, v in zip(y, vals):
        ax.text(v * 1.18, yi, f'{v / 1e6:.2f} MB/day' if v >= 1e6 else f'{v / 1e3:.0f} kB/day',
                va='center', fontsize=11)
    ax.set_xlim(1e4, 3e8)
    ax.set_xlabel('payload bytes per day (log scale)')
    ax.set_title('B3  What leaves the implant per day (computed from the protocol sizes)')
    ax.text(0.0, -0.19, 'Not measured on air: payload size × packet rate; BLE headers and acknowledgements add a few %. '
                        'RAW is off unless requested.', transform=ax.transAxes, fontsize=10, color=C_RULE)
    ax.grid(axis='y', visible=False)
    save(fig, 'B3_bytes_per_day')


# ---- figure C1 -------------------------------------------------------------
def fig_c1():
    log("[C1] text from docs/STEP_D_SUMMARY.md ('What is not proven yet'), the E1/E2/W reports' open questions "
        '(watch: tasks/W3..W5_report.md) and README.md; no dates, no numbers')
    cols = [
        ('Validated (measured)', '#e8f1e8', [
            '5-fold CV by person (3 seeds, 8 classes): 8 real datasets + simulation',
            'fast walking called stairs falls sharply (Lencioni fast, Luo level)',
            'stairs recall and precision on Luo; weaker on PAMAP2',
            'C features = numpy reference; chip host test PASS',
            'BLE protocol v2 and the PC app v2: tests and builds PASS',
            'firmware flash and RAM measured (NCS 3.1.0)']),
        ('Simulated only', '#fdf3df', [
            'transition events (sit-to-stand, stand-to-sit)',
            'bed transfer class',
            'daily metrics and the 40-byte summary streams',
            'posture split, which depends on the detected events']),
        ('Not yet tested', '#f7e6e6', [
            'real device recordings with the live-viewer truth keys',
            'watch live view on hardware (3 BLE bugs fixed, final check pending)',
            'V4 implant firmware: flashed, BLE v2 service seen by the watch; live classes not yet checked against truth',
            'spacer-period gait (walker, crutches)',
            'sitting vs standing split on real people',
            'the watch as a full bridge (no RAW forwarding)',
            "retraining with the owner's own recordings",
            'energy and battery life on the implant',
            '4 s window latency on the device']),
    ]
    fig, ax = plt.subplots(figsize=(12, 6.75))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    texts = ['\n'.join(textwrap.fill(it, 34, initial_indent='•  ', subsequent_indent='   ') for it in items)
             for _, _, items in cols]
    fig_h = axes_height_in(ax)
    lh = 10.0 * 1.45 / 72.0 / fig_h
    h = 0.060 + max(t.count('\n') + 1 for t in texts) * lh
    w = 0.30
    y = 0.93 - h
    for i, ((title, fc, _), text) in enumerate(zip(cols, texts)):
        x = 0.02 + i * 0.325
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.008,rounding_size=0.02',
                                    linewidth=1.2, edgecolor='#777777', facecolor=fc))
        ax.text(x + w / 2, y + h - 0.012, title, ha='center', va='top', fontsize=13, fontweight='bold')
        ax.text(x + 0.010, y + h - 0.055, text, ha='left', va='top', fontsize=10, linespacing=1.45)
    ax.set_title('C1  Where the evidence stands and what comes next', fontsize=13)
    save(fig, 'C1_future_work')


# ---- main ------------------------------------------------------------------
# ---- overview (one slide) ---------------------------------------------------
_CARDS = []          # (card_ax, name) for the layout check
_CARD_INSETS = []    # (card_ax, inset_ax)
_MARKERS = []        # (axes, xs, ys, text) value labels that must not sit on a marker


def _card(fig, ax, letter, title):
    """Very light rounded card with a panel letter and a title; x and y run 0..1 inside it.

    The letter sits 0.04 in from the left edge and the title follows 0.20 in later, in inches, so the gap is
    the same on every card whatever its width."""
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    bb = ax.get_position()
    fig.patches.append(FancyBboxPatch((bb.x0, bb.y0), bb.width, bb.height, transform=fig.transFigure,
                                      boxstyle='round,pad=0.0,rounding_size=0.010', facecolor='#f6f8fb',
                                      edgecolor='#e1e4e9', linewidth=0.8, zorder=-10, clip_on=False))
    w_in = bb.width * fig.get_size_inches()[0]
    lx = 0.040 / w_in
    tx = 0.040 / w_in + 0.160 / w_in + 0.040 / w_in      # edge + letter width + gap
    if letter:
        ax.text(lx, 0.982, letter, fontsize=12, fontweight='bold', va='top', ha='left', color='#8a8f98')
    if title:
        ax.text(tx, 0.982, title, fontsize=12, fontweight='bold', va='top', ha='left', color=C_INK)
    _CARDS.append((ax, f'{letter} {title}'))


def check_layout(fig):
    """Every text inside its card and inside the figure, no two texts overlapping. Printed and logged."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    problems = []
    texts = []
    for t in fig.findobj(mtext.Text):
        if not t.get_visible() or not t.get_text().strip():
            continue
        try:
            e = t.get_window_extent(rend)
        except Exception:
            continue
        if e.width <= 0 or e.height <= 0:
            continue
        texts.append((t, e))
    for t, e in texts:
        if (e.x0 < fig.bbox.x0 - 1 or e.x1 > fig.bbox.x1 + 1 or
                e.y0 < fig.bbox.y0 - 1 or e.y1 > fig.bbox.y1 + 1):
            problems.append(f'outside the figure: {t.get_text()[:40]!r}')
    for cax, name in _CARDS:
        cb = cax.get_window_extent()
        group = list(cax.texts)
        axes_here = [cax] + [ins for c2, ins in _CARD_INSETS if c2 is cax]
        for a in axes_here:
            tb = a.get_tightbbox(rend)
            if tb is None:
                continue
            if (tb.x0 < cb.x0 - 1 or tb.x1 > cb.x1 + 1 or tb.y0 < cb.y0 - 1 or tb.y1 > cb.y1 + 1):
                problems.append(f'{name}: the axes box (ticks/labels included) spills out of the card: '
                                f'axes {tb.x0:.0f},{tb.y0:.0f}..{tb.x1:.0f},{tb.y1:.0f} vs card '
                                f'{cb.x0:.0f},{cb.y0:.0f}..{cb.x1:.0f},{cb.y1:.0f}')
        for c2, ins in _CARD_INSETS:
            if c2 is cax:
                group += list(ins.texts)
        for t in group:
            if not t.get_visible() or not t.get_text().strip():
                continue
            e = t.get_window_extent(rend)
            if (e.x0 < cb.x0 - 1 or e.x1 > cb.x1 + 1 or e.y0 < cb.y0 - 1 or e.y1 > cb.y1 + 1):
                problems.append(f'{name}: text outside the card: {t.get_text()[:40]!r}')
    # minimum gaps, in inches at the figure dpi: 6 px of a 300 dpi print = 0.02 in
    gap_min = 0.020
    min_pair = (99.0, '')
    for i in range(len(texts)):
        a, ea = texts[i]
        for j in range(i + 1, len(texts)):
            b, eb = texts[j]
            dx = max(eb.x0 - ea.x1, ea.x0 - eb.x1)
            dy = max(eb.y0 - ea.y1, ea.y0 - eb.y1)
            g = max(dx, dy) / fig.dpi
            if g < min_pair[0]:
                min_pair = (g, f'{a.get_text()[:20]!r} / {b.get_text()[:20]!r}')
            if g < gap_min:
                problems.append(f'texts too close ({g * 1000:.0f} mil): '
                                f'{a.get_text()[:26]!r} / {b.get_text()[:26]!r}')
    min_edge = (99.0, '')
    for cax, name in _CARDS:
        cb = cax.get_window_extent()
        group = list(cax.texts)
        for c2, ins in _CARD_INSETS:
            if c2 is cax:
                group += list(ins.texts)
        for t in group:
            if not t.get_visible() or not t.get_text().strip():
                continue
            e = t.get_window_extent(rend)
            m = min(e.x0 - cb.x0, cb.x1 - e.x1, e.y0 - cb.y0, cb.y1 - e.y1) / fig.dpi
            if m < min_edge[0]:
                min_edge = (m, f'{name}: {t.get_text()[:20]!r}')
            if m < gap_min:
                problems.append(f'{name}: text only {m * 1000:.0f} mil inside the card edge: '
                                f'{t.get_text()[:30]!r}')
    hits = 0
    for ax_m, xs, ys, label in _MARKERS:
        e = label.get_window_extent(rend)
        for x, y in zip(xs, ys):
            px, py = ax_m.transData.transform((x, y))
            if e.x0 - 1 <= px <= e.x1 + 1 and e.y0 - 1 <= py <= e.y1 + 1:
                hits += 1
                problems.append(f'label {label.get_text()[:12]!r} sits on a marker')
    log(f'  layout check: {len(texts)} texts, {len(_CARDS)} cards, {hits} label/marker hit(s), '
        f'{len(problems)} problem(s); smallest text-text gap {min_pair[0] * 1000:.0f} mil ({min_pair[1]}), '
        f'smallest text-card margin {min_edge[0] * 1000:.0f} mil ({min_edge[1]})')
    for p in problems[:25]:
        log('    ' + p)
    if len(problems) > 25:
        log(f'    ... {len(problems) - 25} more')
    return problems


def fig_overview(lookup, people, sz, proto):
    """The graphical abstract: data, implant, chip, link, results, status."""
    log('[overview] sources: people = windows_v11/windows_W4s.npz (distinct groups); walking/stairs/called = '
        'D2 pred_* + windows_v11 with stairs_rule (0.6) and D3 stairs_rule_results.csv (today); window-length curves = '
        'D3 stairs_rule_results.csv + D3 transition_events_results.csv; sizes = tasks/E2_report.md; packet sizes = '
        '../kneil_firmware/protocol/kneil_proto.h; colours = ../kneil_firmware/pc_app/kneil/protocol.py')
    _CARDS.clear()
    _CARD_INSETS.clear()
    _MARKERS.clear()

    fig = plt.figure(figsize=(13.333, 7.5), facecolor='white')
    gs = fig.add_gridspec(3, 12, left=0.020, right=0.980, top=0.872, bottom=0.075,
                          height_ratios=[2.00, 2.45, 1.05], hspace=0.17, wspace=0.26)

    # ---------------------------------------------------------------- band 1
    ds_order = ['WearGait-PD', 'Lencioni', 'Caicedo older adults', 'CeTI', 'Luo', 'KneE-PAD',
                'MHEALTH', 'PAMAP2', 'Marpino']
    ds_col = ['#0072b2', '#e69f00', '#00923f', '#cc79a7', '#56b4e9', '#d55e00', '#7d5ba6', '#8b5a2b', '#6b7280']
    short_a = {'WearGait-PD': 'WearGait', 'Caicedo older adults': 'Caicedo', 'Lencioni': 'Lencioni',
               'CeTI': 'CeTI', 'Luo': 'Luo', 'KneE-PAD': 'KneE-PAD', 'MHEALTH': 'MHEALTH',
               'PAMAP2': 'PAMAP2', 'Marpino': 'Marpino'}
    ds_short = {'WearGait-PD': 'WearGait-PD', 'Lencioni': 'Lencioni', 'Caicedo older adults': 'Caicedo',
                'CeTI': 'CeTI', 'Luo': 'Luo', 'KneE-PAD': 'KneE-PAD', 'MHEALTH': 'MHEALTH', 'PAMAP2': 'PAMAP2',
                'Marpino': 'Marpino'}
    counts = [people[d] for d in ds_order]
    n_real = int(sum(counts))
    n_sim = int(people['v1.6 synthetic'] + people['Camargo simulated'])

    # (a) data waffle
    ax = fig.add_subplot(gs[0, 0:3])
    _card(fig, ax, 'a', 'Data')
    ax.text(0.030, 0.827, f'{n_real} people + {n_sim} sim.', fontsize=9.5, fontweight='bold', va='top')
    iax = ax.inset_axes([0.020, 0.040, 0.560, 0.660])
    _CARD_INSETS.append((ax, iax))
    ncols = 20
    xs, ys, cs = [], [], []
    for c, n in zip(ds_col, counts):
        for _ in range(n):
            i = len(xs); xs.append(i % ncols); ys.append(i // ncols); cs.append(c)
    for _ in range(n_sim):
        i = len(xs); xs.append(i % ncols); ys.append(i // ncols)
    nrows = int(np.ceil((n_real + n_sim) / ncols))
    iax.scatter(xs[:n_real], ys[:n_real], s=10, c=cs, marker='o', linewidths=0)
    iax.scatter(xs[n_real:], ys[n_real:], s=10, facecolors='none', edgecolors='#a3a8b0', linewidths=0.7, marker='o')
    iax.set_xlim(-0.6, ncols - 0.4)
    iax.set_ylim(nrows - 0.4, -0.6)
    iax.set_aspect('equal')
    iax.set_axis_off()
    entries = [(f'\u25a0 {short_a[d]} {n}', c) for d, n, c in zip(ds_order, counts, ds_col)]
    entries.append((f'\u25a1 simulated {n_sim}', '#a3a8b0'))
    for k, (txt, c) in enumerate(entries):
        ax.text(0.600, 0.835 - k * 0.083, txt, fontsize=9, color=c, va='top')
    log(f'   (a) people: ' + ', '.join(f'{d}={n}' for d, n in zip(ds_order, counts)) +
        f'; total real={n_real}; simulated={people["v1.6 synthetic"]}+{people["Camargo simulated"]}={n_sim}')

    # (b) virtual implant schematic
    ax = fig.add_subplot(gs[0, 3:6])
    _card(fig, ax, 'b', 'Virtual implant')
    iax = ax.inset_axes([0.01, 0.03, 0.48, 0.77])
    _CARD_INSETS.append((ax, iax))
    iax.set_xlim(0, 1)
    iax.set_ylim(0, 1)
    iax.set_axis_off()
    iax.add_patch(FancyBboxPatch((0.30, 0.72), 0.38, 0.25, boxstyle='round,pad=0,rounding_size=0.06',
                                 facecolor='#dde1e7', edgecolor='none'))
    iax.add_patch(FancyBboxPatch((0.27, 0.625), 0.44, 0.075, boxstyle='round,pad=0,rounding_size=0.025',
                                 facecolor='#cfe0f2', edgecolor='none'))
    iax.add_patch(FancyBboxPatch((0.32, 0.10), 0.34, 0.50, boxstyle='round,pad=0,rounding_size=0.05',
                                 facecolor='#dde1e7', edgecolor='none'))
    iax.add_patch(FancyBboxPatch((0.335, 0.17), 0.10, 0.065, boxstyle='round,pad=0,rounding_size=0.02',
                                 facecolor=C_V4_NORULE, edgecolor='none'))
    iax.plot([0.385, 0.55], [0.2025, 0.565], ls='--', lw=0.9, color=C_RULE, zorder=3)
    iax.text(0.468, 0.335, 'r', fontsize=9, color=C_RULE, style='italic',
             bbox=dict(facecolor='white', edgecolor='none', pad=0.6))
    iax.add_patch(Circle((0.55, 0.565), 0.030, facecolor=C_V4, edgecolor='white', linewidth=0.9, zorder=5))
    iax.annotate('', xy=(0.78, 0.565), xytext=(0.585, 0.565),
                 arrowprops=dict(arrowstyle='-|>', lw=1.0, color=C_INK, shrinkA=0, shrinkB=0))
    iax.text(0.600, 0.360, 'x anterior', fontsize=9, ha='left')
    iax.annotate('', xy=(0.55, 0.82), xytext=(0.55, 0.60),
                 arrowprops=dict(arrowstyle='-|>', lw=1.0, color=C_INK, shrinkA=0, shrinkB=0))
    iax.text(0.610, 0.725, 'z up', fontsize=9)
    iax.text(0.720, 0.930, 'femur', fontsize=9, va='center')
    iax.annotate('spacer', xy=(0.270, 0.662), xytext=(0.020, 0.800), fontsize=9, va='center', ha='left',
                 arrowprops=dict(arrowstyle='-', lw=0.7, color=C_RULE, shrinkA=1, shrinkB=1))
    iax.text(0.700, 0.260, 'tibia', fontsize=9, va='center')
    iax.text(0.575, 0.545, 'implant', fontsize=9, va='top')
    iax.annotate('shank IMU', xy=(0.40, 0.19), xytext=(0.02, 0.02), fontsize=9,
                 arrowprops=dict(arrowstyle='-', lw=0.7, color=C_RULE, shrinkA=0, shrinkB=0))
    ax.text(0.520, 0.840, 'f_P = f_S + α×r', fontsize=9.5, va='top')
    ax.text(0.545, 0.748, '+ ω×(ω×r)', fontsize=9.5, va='top')
    ax.text(0.520, 0.660, 'validated on\nCamargo, 22 people:\n|a| r = 0.93\n0.27 g RMS', fontsize=9, va='top',
            color=C_RULE, linespacing=1.35)
    ax.text(0.520, 0.280, 'implant point:\n2.5 cm below the\njoint, 5 mm anterior', fontsize=9, va='top',
            color=C_RULE, linespacing=1.3)

    # (c) on the chip
    ax = fig.add_subplot(gs[0, 6:9])
    _card(fig, ax, 'c', 'On the chip')
    steps = ['50 Hz accelerometer, ±8 g', 'causal 6 Hz low-pass', '4 s window, 1 s hop', '20 features (C code)',
             'forest 20 × depth 10', 'stairs rule: vote ≥ 0.6', 'events (R1) + summary']
    for i, s in enumerate(steps):
        y = 0.883 - i * 0.0861
        ax.text(0.105, y, s, fontsize=9, va='top')
        if i < len(steps) - 1:
            ax.annotate('', xy=(0.070, y - 0.062), xytext=(0.070, y - 0.020),
                        arrowprops=dict(arrowstyle='-|>', lw=0.9, color='#9aa0a6', shrinkA=0, shrinkB=0))
    ax.text(0.06, 0.280, f'forest {sz["forest_bytes"] / 1000:.0f} kB flash\nclassifier '
                         f'{sz["classifier"] / 1000:.1f} kB RAM', fontsize=9, fontweight='bold', color=C_V4, va='top',
            linespacing=1.15)
    ax.text(0.06, 0.110, f'firmware {sz["fw_flash"] / 1000:.0f} kB flash / {sz["fw_ram"] / 1000:.0f} kB RAM',
            fontsize=9, color=C_RULE, va='top')
    log(f'   (c) sizes: forest {sz["forest_bytes"]} B, classifier {sz["classifier"]} B, firmware '
        f'{sz["fw_flash"]} B flash / {sz["fw_ram"]} B RAM (tasks/E2_report.md)')

    # (d) live view
    ax = fig.add_subplot(gs[0, 9:12])
    _card(fig, ax, 'd', 'Live view')

    def small_box(x, y, w, h, text, fc='#ffffff', ec='#c9ced6'):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.004,rounding_size=0.02',
                                    facecolor=fc, edgecolor=ec, linewidth=0.8))
        ax.text(x + w / 2, y + h / 2, text, fontsize=9, ha='center', va='center', linespacing=1.25)

    small_box(0.05, 0.725, 0.90, 0.100, 'implant: V4 classes + daily metrics')
    small_box(0.05, 0.520, 0.90, 0.145, 'BLE v2\nLIVE 22 B/s · SUMMARY 41 B/min · INFO')
    small_box(0.02, 0.305, 0.44, 0.100, 'XIAO bridge')
    small_box(0.02, 0.095, 0.44, 0.155, 'PC app: live view,\ntruth keys, recording')
    small_box(0.540, 0.095, 0.440, 0.310, 'Güder watch\nKNEIL mode\n(direct BLE)')
    for (x0, y0, x1, y1) in [(0.50, 0.725, 0.50, 0.674), (0.24, 0.520, 0.24, 0.414),
                             (0.24, 0.305, 0.24, 0.259), (0.76, 0.520, 0.76, 0.414)]:
        ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle='-|>', lw=1.0, color='#7c828b', shrinkA=0, shrinkB=0))
    log(f'   (d) protocol: LIVE {proto["live"]} B/s, SUMMARY {proto["summary"]} B/min, INFO text; RAW '
        f'{proto["raw_hdr"] + 6 * proto["raw_n"]} B/0.5 s on request (not shown)')

    # ---------------------------------------------------------------- band 2
    # (e) key numbers
    luo_t, luo_v = lookup('V3recipe', 2, 'before', 'called', 'Luo', 'surface=FE', 'walking_called_stairs_pct')[0], \
                   lookup('V4half', 4, 'after_06', 'called', 'Luo', 'surface=FE', 'walking_called_stairs_pct')[0]
    len_t, len_v = lookup('V3recipe', 2, 'before', 'called', 'Lencioni', 'speed_abs=fast',
                          'walking_called_stairs_pct')[0], \
                   lookup('V4half', 4, 'after_06', 'called', 'Lencioni', 'speed_abs=fast',
                          'walking_called_stairs_pct')[0]
    wg_t, wg_v = lookup('V3recipe', 2, 'before', 'called', 'WearGait-PD', 'rec=HurriedPace',
                        'walking_called_stairs_pct')[0], \
                 lookup('V4half', 4, 'after_06', 'called', 'WearGait-PD', 'rec=HurriedPace',
                        'walking_called_stairs_pct')[0]

    ax = fig.add_subplot(gs[1, 0:2])
    _card(fig, ax, 'e', 'Key numbers')
    ax.text(0.045, 0.860, 'walking called stairs (%)', fontsize=9, color=C_RULE, va='top')
    for i, (name, a_, b_) in enumerate([('Luo level walking', luo_t, luo_v), ('Lencioni fast', len_t, len_v),
                                        ('WearGait-PD hurried', wg_t, wg_v)]):
        y_lab = 0.765 - i * 0.240
        y_num = 0.545 - i * 0.240
        ax.text(0.045, y_lab, name, fontsize=9, va='top')
        ax.text(0.045, y_num + 0.005, f'{a_:.1f}', fontsize=9, va='bottom', color=C_TODAY)
        ax.text(0.220, y_num + 0.005, '\u2192', fontsize=9, va='bottom', color=C_RULE)
        ax.text(0.310, y_num, f'{b_:.1f}', fontsize=24, va='bottom', color=C_V4, fontweight='bold')
    log(f'   (e) key numbers: Luo FE {luo_t:.2f} -> {luo_v:.2f}, Lencioni fast {len_t:.2f} -> {len_v:.2f}, '
        f'WearGait hurried {wg_t:.2f} -> {wg_v:.2f}')

    # (f) walking dumbbells
    ax = fig.add_subplot(gs[1, 2:5])
    _card(fig, ax, 'f', 'Walking recognised')
    # the CV tables cover the 8 real datasets that were trained on (Caicedo is the external marker set)
    ds_walk = ['WearGait-PD', 'Lencioni', 'Luo', 'KneE-PAD', 'MHEALTH', 'PAMAP2', 'Marpino', 'CeTI']
    short_f = {'WearGait-PD': 'WearGait'}
    rows_f = []
    for d in ds_walk + ['simulated']:
        t_ = lookup('V3recipe', 2, 'before', 'walking', d, 'walking', 'recall_pct')[0]
        v_ = lookup('V4half', 4, 'after_06', 'walking', d, 'walking', 'recall_pct')[0]
        rows_f.append((d, people.get(d, 0), t_, v_))
    rows_f.sort(key=lambda r: -r[3])
    iax = ax.inset_axes([0.335, 0.191, 0.635, 0.632])
    _CARD_INSETS.append((ax, iax))
    for i, (d, n, t_, v_) in enumerate(rows_f):
        y = len(rows_f) - 1 - i
        iax.plot([t_, v_], [y, y], color='#d7dade', lw=2.4, solid_capstyle='round', zorder=1)
        iax.scatter([t_], [y], s=26, color=C_TODAY, zorder=2)
        iax.scatter([v_], [y], s=30, color=C_V4, zorder=3)
        lab = iax.text(v_ + 2.5, y, f'{v_:.0f}', fontsize=9, va='center', color=C_INK)
        _MARKERS.append((iax, [t_, v_], [y, y], lab))
    labels = []
    for d, n, t_, v_ in rows_f:
        if d == 'simulated':
            labels.append('simulated*')
        else:
            labels.append(f'{short_f.get(d, ds_short[d])} {n}' + ('\u2020' if n < 10 else ''))
    iax.set_xlim(0, 120)
    iax.set_ylim(-0.7, len(rows_f) - 0.3)
    iax.set_yticks(range(len(rows_f)))
    iax.set_yticklabels(labels[::-1], fontsize=9)
    # style each row from its own data (the labels are set bottom-up, the rows top-down)
    for tick, (d, n, t_, v_) in zip(iax.get_yticklabels(), rows_f[::-1]):
        if d == 'simulated':
            tick.set_style('italic')
        elif n < 10:
            tick.set_color(C_BAD)
    red = [x for x in iax.get_yticklabels() if to_hex(x.get_color()) == C_BAD]
    ital = [x for x in iax.get_yticklabels() if x.get_style() == 'italic']
    assert red and all('\u2020' in x.get_text() for x in red), [x.get_text() for x in red]
    assert len(ital) == 1 and ital[0].get_text() == 'simulated*', [x.get_text() for x in ital]
    iax.tick_params(axis='x', labelsize=9, length=2, pad=1)
    iax.tick_params(axis='y', length=0, pad=1.5)
    iax.set_xticks([0, 50, 100])
    iax.set_xlabel('recall (%)', fontsize=9, labelpad=1.5)
    iax.grid(axis='x', color='#e8eaee', lw=0.6)
    iax.set_axisbelow(True)
    ax.text(0.40, 0.895, '\u25cf today', fontsize=9, color=C_TODAY, va='top')
    ax.text(0.66, 0.895, '\u25cf V4 + rule', fontsize=9, color=C_V4, va='top')
    log('   (f) walking recall: ' + ', '.join(f'{d}={t_:.1f}->{v_:.1f}' for d, _, t_, v_ in rows_f))
    log('   (f) styles: red=' + ', '.join(x.get_text() for x in red) + '; italic=' + ital[0].get_text())

    # (g) stairs dumbbells
    ax = fig.add_subplot(gs[1, 5:9])
    _card(fig, ax, 'g', 'Stairs: the honest trade-off')
    groups_g = [('Luo', 'stairs_up', 'Luo up'), ('Luo', 'stairs_down', 'Luo down'),
                ('PAMAP2', 'stairs_up', 'PAMAP2\u2020 up'), ('PAMAP2', 'stairs_down', 'PAMAP2\u2020 down')]
    rows_g = []
    for ds, key, name in groups_g:
        for metric, lab in (('recall_pct', 'recall'), ('precision_pct', 'prec.')):
            t_ = lookup('V3recipe', 2, 'before', 'stairs', ds, key, metric)[0]
            v_ = lookup('V4half', 4, 'after_06', 'stairs', ds, key, metric)[0]
            rows_g.append((f'{name} \u00b7 {lab}', t_, v_))
    iax = ax.inset_axes([0.380, 0.306, 0.600, 0.570])
    _CARD_INSETS.append((ax, iax))
    for i, (name, t_, v_) in enumerate(rows_g):
        y = len(rows_g) - 1 - i
        iax.plot([t_, v_], [y, y], color='#d7dade', lw=2.4, solid_capstyle='round', zorder=1)
        iax.scatter([t_], [y], s=26, color=C_TODAY, zorder=2)
        iax.scatter([v_], [y], s=30, color=C_V4, zorder=3)
        left = v_ < t_
        lab = iax.text(v_ + (-2.5 if left else 2.5), y, f'{v_:.0f}', fontsize=9, va='center',
                       ha='right' if left else 'left', color=C_BAD if left else C_INK)
        _MARKERS.append((iax, [t_, v_], [y, y], lab))
    iax.set_xlim(-3, 103)
    iax.set_ylim(-0.7, len(rows_g) - 0.3)
    iax.set_yticks(range(len(rows_g)))
    iax.set_yticklabels([r[0] for r in rows_g][::-1], fontsize=9)
    iax.tick_params(axis='x', labelsize=9, length=2, pad=1)
    iax.tick_params(axis='y', length=0, pad=1.5)
    iax.set_xticks([0, 50, 100])
    iax.grid(axis='x', color='#e8eaee', lw=0.6)
    iax.set_axisbelow(True)
    # the cost, in words, from the same numbers (Luo up/down, PAMAP2 up/down; rows 0-7)
    note = (f'Precision rises on Luo (up {rows_g[1][1]:.0f}\u2192{rows_g[1][2]:.0f}, '
            f'down {rows_g[3][1]:.0f}\u2192{rows_g[3][2]:.0f}). Recall falls for Luo stairs up '
            f'({rows_g[0][1]:.0f}\u2192{rows_g[0][2]:.0f}) and on PAMAP2 (7): up {rows_g[4][1]:.0f}\u2192{rows_g[4][2]:.0f}, '
            f'down {rows_g[6][1]:.0f}\u2192{rows_g[6][2]:.0f}; its stairs-up precision stays '
            f'{rows_g[5][1]:.0f}\u2192{rows_g[5][2]:.0f}.')
    ax.text(0.030, 0.225, textwrap.fill(note, 58), fontsize=9, color='#b26a00', va='top', linespacing=1.15)
    log('   (g) stairs (today -> V4+rule): ' + ', '.join(f'{n}={t_:.1f}->{v_:.1f}' for n, t_, v_ in rows_g))
    log('   (g) note: ' + note)

    # (h) window length
    rule = pd.read_csv(os.path.join(STEPD, 'D3', 'stairs_rule_results.csv'))
    events = pd.read_csv(os.path.join(STEPD, 'D3', 'transition_events_results.csv'))
    f05 = rule[(rule.variant == 'V4half') & (rule.stage == 'after_f05') & (rule.table == 'merged') &
               (rule.dataset == 'Luo') & (rule.key == 'stairs') & (rule.metric == 'f05_pct')].sort_values('win')
    ev = events[(events.variant == 'V4half') & (events.rule == 'R1') & (events.table == 'events') &
                (events.source == 'simulation') & (events.metric == 'event_recall_pct')].sort_values('win')
    ax = fig.add_subplot(gs[1, 9:12])
    _card(fig, ax, 'h', 'Window length')
    iax = ax.inset_axes([0.135, 0.235, 0.680, 0.545])
    _CARD_INSETS.append((ax, iax))
    iax.plot(f05.win, f05.value, '-o', color=C_V4, lw=1.8, ms=5)
    iax.plot(ev.win, ev.value, '-s', color='#c98a00', lw=1.8, ms=4.5)
    iax.axvline(4, color=C_RULE, ls='--', lw=0.9)
    iax.set_xlim(1.8, 7.2)
    iax.set_ylim(56, 94)
    f4 = float(f05[f05.win == 4].iloc[0].value)
    e4 = float(ev[ev.win == 4].iloc[0].value)
    iax.annotate(f'{f4:.0f}', (4, f4), textcoords='offset points', xytext=(8, 6), fontsize=9, color=C_V4)
    iax.annotate(f'{e4:.0f}', (4, e4), textcoords='offset points', xytext=(8, -13), fontsize=9, color='#c98a00')
    iax.text(5.15, float(f05.value.iloc[-1]), 'stairs F0.5', fontsize=9, color=C_V4, va='center')
    iax.text(5.15, float(ev.value.iloc[-1]), 'STS (sim.)', fontsize=9, color='#c98a00', va='center')
    iax.set_xticks([2, 3, 4, 5])
    iax.set_yticks([60, 70, 80, 90])
    iax.tick_params(labelsize=9, length=2, pad=1)
    iax.set_xlabel('window (s)', fontsize=9, labelpad=1.5)
    iax.set_ylabel('%', fontsize=9, labelpad=1.5)
    iax.grid(color='#e8eaee', lw=0.6)
    iax.set_axisbelow(True)
    log('   (h) window: F0.5 ' + ', '.join(f'{w:g}s={v:.1f}' for w, v in zip(f05.win, f05.value)) +
        '; STS ' + ', '.join(f'{w:g}s={v:.1f}' for w, v in zip(ev.win, ev.value)))

    # ---------------------------------------------------------------- band 3
    ax = fig.add_subplot(gs[2, 0:12])
    _card(fig, ax, '', '')
    lanes = [
        ('Measured', '#eef6ee', '#2e7d32', [
            'CV by person: 8 real datasets + simulation',
            'chip C code = Python model (host test PASS)',
            f'firmware built: {sz["fw_flash"] / 1000:.0f} kB flash, {sz["fw_ram"] / 1000:.0f} kB RAM',
            'BLE protocol v2 and PC app tests PASS']),
        ('Simulated only', '#fdf6e3', '#b26a00', [
            'sit-to-stand / stand-to-sit events',
            '78 % recall at 4 s; 0.9 false events per hour',
            'bed transfer class',
            'posture split from the detected events']),
        ('Not yet tested', '#fbeceb', '#b2182b', [
            'recordings with the truth keys on the real device',
            'sitting vs standing split on real people',
            'spacer-period gait (walker, crutches)',
            'energy and battery on the implant']),
    ]
    for k, (title, fc, ec, items) in enumerate(lanes):
        x = 0.012 + k * 0.331
        ax.add_patch(FancyBboxPatch((x, 0.175), 0.320, 0.805, boxstyle='round,pad=0.004,rounding_size=0.03',
                                    facecolor=fc, edgecolor=ec, linewidth=0.8))
        ax.text(x + 0.012, 0.950, title, fontsize=9.5, fontweight='bold', color=ec, va='top')
        ax.text(x + 0.012, 0.780, '\n'.join('\u2022  ' + it for it in items), fontsize=9, va='top',
                linespacing=1.1)
    ax.text(0.012, 0.175, "Owner's watch log, 17 Nov 2026: the implant runs the V4 firmware (the watch found "
                          'its protocol-v2 SUMMARY characteristic); the watch live view needed three BLE fixes, final '
                          'check pending.', fontsize=9, color=C_RULE, style='italic', va='top')
    log('   (i) status lanes: 4 measured, 3 simulated-only, 4 not yet tested; the watch-log line is the manager\'s '
        'fact (owner\'s log, 17 Nov 2026)')

    # ---------------------------------------------------------------- header, band labels, footer
    fig.text(0.020, 0.985, 'KNEIL V4: an implant that tells walking from stairs', fontsize=20,
             fontweight='bold', va='top', color=C_INK)
    fig.text(0.020, 0.944, 'activity recognition in an instrumented knee spacer: data, chip, link and results '
                           '(Nov 2026)', fontsize=11, color=C_RULE, va='top')
    band_labels = [(fig.axes[0], '1 · HOW IT WORKS'),
                   (fig.axes[4], '2 · WHAT CHANGED — 5-FOLD CV BY PERSON, MEAN OF 3 SEEDS'),
                   (fig.axes[8], '3 · WHERE IT STANDS')]
    for rax, text in band_labels:
        bb = rax.get_position()
        fig.text(0.021, bb.y1 + 0.006, text, fontsize=9, color='#6b7280', fontweight='bold', va='bottom')
    fig.text(0.020, 0.014, 'Today = V3recipe, 2 s windows. V4 = new data at half weight, 4 s windows, stairs only if '
                           '≥ 60 % of the trees agree. Simulated = 60 synthetic personas + Camargo replay. '
                           'Sources: docs/FIGURES.md.', fontsize=8, color='#6b7280', va='bottom')

    problems = check_layout(fig)
    save(fig, 'OVERVIEW_kneil_v4', pdf=True, svg_paths=True)
    if problems:
        raise SystemExit('overview: layout problems, see the log above')


def main():
    ap = argparse.ArgumentParser(description='KNEIL V4 figures (see docs/FIGURES.md)')
    ap.add_argument('--only', choices=['overview', 'a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'b2', 'b3', 'c1'],
                    help='write one figure only (default: all of them)')
    args = ap.parse_args()
    want = {args.only} if args.only else {'overview', 'a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'b2', 'b3', 'c1'}

    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    log(f'KNEIL figures, {VERSION}   {datetime.datetime.now():%Y-%m-%d %H:%M}')
    log(f'python {sys.version.split()[0]}, matplotlib {matplotlib.__version__}, numpy {np.__version__}, '
        f'pandas {pd.__version__}')
    log(f'step D results: {STEPD}')
    if args.only:
        log(f'only: {args.only}')
    style()
    labels, cols = protocol_colours()
    proto = protocol_sizes()
    sz = e2_sizes()

    A4 = windows(4)[0]
    people = people_counts(A4)

    G_before = {('V3recipe', 2): agg(rule_tables(2, 'V3recipe', None)),
                ('V4half', 4): agg(rule_tables(4, 'V4half', None))}
    G_after = agg(rule_tables(4, 'V4half', 0.6))
    lookup = make_lookup(G_before, G_after)

    if 'overview' in want: fig_overview(lookup, people, sz, proto)
    if 'a1' in want: fig_a1(lookup)
    if 'a2' in want: fig_a2(lookup, people)
    if 'a3' in want: fig_a3(lookup)
    if 'a4' in want: fig_a4()
    if 'a5' in want: fig_a5(confusion(4, 'V4half', 0.6), labels, cols)
    if 'b1' in want: fig_b1(people)
    if 'b2' in want: fig_b2(sz, proto)
    if 'b3' in want: fig_b3(sz, proto)
    if 'c1' in want: fig_c1()

    log(f'done in {time.time() - t0:.1f} s; figures in {OUT}')
    open(LOG_PATH, 'w', encoding='utf-8').write('\n'.join(_LOG) + '\n')


if __name__ == '__main__':
    main()
