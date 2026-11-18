#!/usr/bin/env python
"""
KNEIL V4 figures for talks, meetings and the thesis draft.   make_figures 1.0, 18 Nov 2026

Reads the step D result files and the E2 build report and writes nine figures as PNG (300 dpi) and SVG to
docs/figures/.  Nothing is trained and no window is rebuilt: the script only reads cached files.

Sources of the numbers (printed per panel, also in docs/figures/make_figures_log.txt):
  KNEIL_results/v4/stepD/D3/stairs_rule_results.csv        (A4; the published before/after tables)
  KNEIL_results/v4/stepD/D3/transition_events_results.csv  (A4: event recall, false events)
  KNEIL_results/v4/stepD/D2/pred_*_W*s_8cls_seed*.npz      (A1-A3, A5: per-window predictions, 3 seeds)
  KNEIL_results/v4/stepD/windows_v11/windows_W{2,4}s.npz   (truth, stream ids, dataset, people)
  tasks/E2_report.md                                       (B2: measured flash / RAM)
  ../kneil_firmware/protocol/kneil_proto.h                 (B3: packet sizes)
  ../kneil_firmware/pc_app/kneil/protocol.py               (class names and colours)

Run: python pipeline/make_figures.py        (about 30 s; needs the step D results on this PC)
"""
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
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch, Patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config
import cv_v4 as C
import stairs_rule as SR

VERSION = 'make_figures 1.0'
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
    print(msg)
    _LOG.append(str(msg))


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + '.png'), dpi=300, bbox_inches='tight', facecolor='white')
    fig.savefig(os.path.join(OUT, name + '.svg'), bbox_inches='tight', facecolor='white')
    plt.close(fig)
    log(f'  wrote {name}.png and {name}.svg')


def style():
    plt.rcParams.update({
        'font.size': 11, 'axes.titlesize': 13, 'axes.labelsize': 11,
        'xtick.labelsize': 11, 'ytick.labelsize': 11, 'legend.fontsize': 10.5,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.edgecolor': '#666666', 'axes.labelcolor': C_INK, 'text.color': C_INK,
        'xtick.color': C_INK, 'ytick.color': C_INK,
        'axes.grid': True, 'grid.color': '#e6e6e6', 'grid.linewidth': 0.8,
        'figure.facecolor': 'white', 'svg.fonttype': 'none',
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
    fig.suptitle("A1  Walking called stairs: the owner's device problem", fontsize=13, y=0.98)
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
            ax.text(v + 1.0, yi, f'{v:.0f}', va='center', fontsize=10)
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

    fig, axes = plt.subplots(3, 1, figsize=(10, 5.6), sharex=True)
    specs = [(axes[0], f05, 'Luo stairs F0.5 (%)', 'higher is better'),
             (axes[1], ev, 'STS recall, simulated (%)', 'higher is better'),
             (axes[2], fl, 'false events per hour', 'lower is better')]
    for ax, d, ylab, note in specs:
        ax.plot(d.win, d.value, '-o', color=C_V4, lw=2, ms=6)
        for w, v in zip(d.win, d.value):
            ax.annotate(f'{v:.1f}', (w, v), textcoords='offset points', xytext=(0, 9), ha='center', fontsize=10)
        ax.axvline(4, color=C_RULE, ls='--', lw=1)
        ax.set_ylabel(ylab, fontsize=10)
        ax.text(0.995, 0.06, note, transform=ax.transAxes, ha='right', fontsize=9.5, color=C_RULE)
        ax.grid(axis='x', visible=False)
        ax.margins(x=0.08, y=0.30)
    axes[2].set_xlabel('window length (s)')
    axes[2].set_xticks([2, 3, 4, 5])
    axes[0].set_title('A4  Window-length trade-off (V4half; mean of 3 seeds, CV by person)')
    axes[0].text(4.06, axes[0].get_ylim()[1], 'chosen: 4 s', fontsize=10.5, color=C_RULE, va='top')
    fig.tight_layout()
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
def box(ax, x, y, w, h, title, body='', ts=11.5, bs=10.0, wrap_b=22, wrap_t=17):
    fig_h = ax.figure.get_size_inches()[1]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.006,rounding_size=0.012',
                                linewidth=1.2, edgecolor='#555555', facecolor='#ffffff'))
    t = textwrap.fill(title, wrap_t) if wrap_t else title
    if body:
        b = '\n'.join(textwrap.fill(line, wrap_b) if line.strip() else '' for line in body.split('\n'))
        lh = bs * 1.45 / 72.0 / fig_h          # line height in axes units
        th = ts * 1.25 / 72.0 / fig_h
        top = y + h - 0.012
        ax.text(x + w / 2, top, t, ha='center', va='top', fontsize=ts, fontweight='bold', color=C_INK)
        ax.text(x + w / 2, top - (t.count('\n') + 1) * th - 0.012, b, ha='center', va='top', fontsize=bs,
                color=C_INK, linespacing=1.45)
    else:
        ax.text(x + w / 2, y + h / 2, t, ha='center', va='center', fontsize=ts, fontweight='bold', color=C_INK)


def arrow(ax, x0, y0, x1, y1):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='-|>', lw=1.5, color='#555555', shrinkA=0, shrinkB=0))


def fig_b1(people):
    src = (f'shank IMUs\nWearGait-PD {people["WearGait-PD"]}\n'
           f'Luo {people["Luo"]}, KneE-PAD {people["KneE-PAD"]}\n'
           f'PAMAP2 {people["PAMAP2"]}, MHEALTH {people["MHEALTH"]}\n\n'
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
    w, h, y = 0.175, 0.78, 0.11
    xs = [0.010, 0.212, 0.414, 0.616, 0.818]
    box(ax, xs[0], y, w, h, 'Public gait data', src, ts=12, bs=10, wrap_b=20, wrap_t=19)
    box(ax, xs[1], y, w, h, 'Virtual implant',
        'rigid-body transfer\nf_P = f_S + a×r + w×(w×r)\n\none tibia frame\nper person\n(z gravity,\ny rotation axis)\n\n'
        'plausibility rule:\nforward lean -5…+35°', ts=11, bs=9)
    box(ax, xs[2], y, w, h, 'Implant signals',
        '3-axis accelerometer\n50 Hz, ±8 g\n\ncausal 6 Hz low-pass\n\n4 s windows, 1 s hop\n(same for every dataset)',
        ts=11, bs=9)
    box(ax, xs[3], y, w, h, 'Model',
        '20 features per window\n(same C code as the chip)\n\nrandom forest\n20 trees × depth 10\n\n'
        '5-fold CV by person\n3 seeds', ts=12, bs=10.5, wrap_b=21, wrap_t=19)
    box(ax, xs[4], y, w, h, 'Export',
        'emlearn\n\nkneil_tinyml v2.0\n\n8 classes\n(4 s window, 1 s hop)\n\nV4half: new data\nat half weight',
        ts=12, bs=10.5, wrap_b=21, wrap_t=19)
    for i in range(4):
        arrow(ax, xs[i] + w + 0.004, y + h / 2, xs[i + 1] - 0.004, y + h / 2)
    ax.set_title('B1  Training data pipeline: from public gait data to the chip library', fontsize=13)
    ax.text(0.5, 0.03, 'people counts from the window file (W4); the simulation mixes synthetic personas and the Camargo replay',
            ha='center', fontsize=10, color=C_RULE)
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

    dev_y, dev_h = 0.62, 0.28
    w = 0.145
    xs = [0.012 + i * 0.163 for i in range(6)]
    dev = [('Accel. sensor', '50 Hz, ±8 g\n3 axes'),
           ('Low-pass', 'causal 6 Hz\non the device'),
           ('Window', '4 s, 1 s hop\n200 samples/axis'),
           ('Features', '20 per window\nsame C code'),
           ('Forest', f'20 × depth 10\n{sz["forest_bytes"]:,} B flash\n{sz["classifier"]:,} B RAM'),
           ('Rule + events', 'stairs vote ≥ 0.6\nR1 events\nposture state')]
    for i, (t, b) in enumerate(dev):
        box(ax, xs[i], dev_y, w, dev_h, t, b, ts=11, bs=10, wrap_b=20, wrap_t=15)
        if i:
            arrow(ax, xs[i - 1] + w + 0.003, dev_y + dev_h / 2, xs[i] - 0.003, dev_y + dev_h / 2)

    dm_x, dm_y, dm_h = xs[5], 0.32, 0.22
    box(ax, dm_x, dm_y, w, dm_h, 'Daily metrics',
        f'posture split, events,\nminutes per class\n{sz["summary"]} B summary', ts=11, bs=10, wrap_b=20, wrap_t=15)
    arrow(ax, dm_x + w / 2, dev_y - 0.005, dm_x + w / 2, dm_y + dm_h + 0.005)

    link_y, link_h, w2 = 0.03, 0.21, 0.155
    xs2 = [0.012, 0.185, 0.358, 0.531, 0.704]
    box(ax, xs2[0], link_y, w2, link_h, 'BLE packets',
        f'LIVE {proto["live"]} B/s\nSUMMARY {proto["summary"]} B/min\nINFO (text)\n'
        f'RAW {proto["raw_hdr"] + 6 * proto["raw_n"]} B / 0.5 s', ts=11, bs=10, wrap_b=20, wrap_t=15)
    box(ax, xs2[1], link_y, w2, link_h, 'XIAO bridge', 'BLE → USB serial\ntext lines', ts=11, bs=10,
        wrap_b=20, wrap_t=15)
    box(ax, xs2[2], link_y, w2, link_h, 'PC app', 'live view,\ntruth keys, recording', ts=11, bs=10,
        wrap_b=20, wrap_t=15)
    box(ax, xs2[4], link_y, w2, link_h, 'Guder watch', 'KNEIL mode:\nlive class, vote,\nposture, events', ts=11, bs=10,
        wrap_b=20, wrap_t=15)

    # device row -> a small bus -> BLE packets
    bus_y = 0.285
    ax.plot([dm_x + w / 2, dm_x + w / 2], [dm_y - 0.005, bus_y], color='#555555', lw=1.5)
    ax.plot([xs2[0] + w2 / 2, dm_x + w / 2], [bus_y, bus_y], color='#555555', lw=1.5)
    arrow(ax, xs2[0] + w2 / 2, bus_y, xs2[0] + w2 / 2, link_y + link_h + 0.005)
    for i in (0, 1, 2):
        arrow(ax, xs2[i] + w2 + 0.004, link_y + link_h / 2, xs2[i + 1] - 0.004, link_y + link_h / 2)
    arrow(ax, xs2[2] + w2 + 0.004, link_y + link_h / 2, xs2[4] - 0.004, link_y + link_h / 2)
    ax.text((xs2[2] + w2 + xs2[4]) / 2, link_y + link_h / 2 + 0.02, 'BLE central', ha='center', fontsize=9.5,
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
    log("[C1] text from docs/STEP_D_SUMMARY.md ('What is not proven yet'), the E1/E2/W reports' open questions and "
        'README.md; no dates, no numbers')
    cols = [
        ('Validated (measured)', '#e8f1e8', [
            '5-fold CV by person, 3 seeds, 8 classes, 9 datasets',
            'fast walking called stairs falls sharply (Lencioni fast, Luo level)',
            'stairs recall and precision on Luo; weaker on PAMAP2',
            'C features = numpy reference; chip host test PASS',
            'BLE protocol v2, PC app v2, watch KNEIL mode: tests and builds PASS',
            'firmware flash and RAM measured (NCS 3.1.0)']),
        ('Simulated only', '#fdf3df', [
            'transition events (sit-to-stand, stand-to-sit)',
            'bed transfer class',
            'daily metrics and the 40-byte summary streams',
            'posture split, which depends on the detected events']),
        ('Not yet tested', '#f7e6e6', [
            'real device recordings with the live-viewer truth keys',
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
    w = 0.30
    for i, (title, fc, items) in enumerate(cols):
        x = 0.02 + i * 0.325
        ax.add_patch(FancyBboxPatch((x, 0.04), w, 0.84, boxstyle='round,pad=0.008,rounding_size=0.02',
                                    linewidth=1.2, edgecolor='#777777', facecolor=fc))
        ax.text(x + w / 2, 0.845, title, ha='center', va='top', fontsize=13, fontweight='bold')
        text = '\n'.join(textwrap.fill(it, 34, initial_indent='•  ', subsequent_indent='   ') for it in items)
        ax.text(x + 0.010, 0.775, text, ha='left', va='top', fontsize=10.5, linespacing=1.6)
    ax.set_title('C1  Where the evidence stands (plan, not results)', fontsize=13)
    save(fig, 'C1_future_work')


# ---- main ------------------------------------------------------------------
def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    log(f'KNEIL figures, {VERSION}   {datetime.datetime.now():%Y-%m-%d %H:%M}')
    log(f'python {sys.version.split()[0]}, matplotlib {matplotlib.__version__}, numpy {np.__version__}, '
        f'pandas {pd.__version__}')
    log(f'step D results: {STEPD}')
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

    fig_a1(lookup)
    fig_a2(lookup, people)
    fig_a3(lookup)
    fig_a4()
    fig_a5(confusion(4, 'V4half', 0.6), labels, cols)
    fig_b1(people)
    fig_b2(sz, proto)
    fig_b3(sz, proto)
    fig_c1()

    log(f'done in {time.time() - t0:.1f} s; figures in {OUT}')
    open(LOG_PATH, 'w', encoding='utf-8').write('\n'.join(_LOG) + '\n')


if __name__ == '__main__':
    main()
