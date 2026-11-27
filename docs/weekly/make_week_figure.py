"""Week-at-a-glance figure for the weekly report (20-26 Nov 2026). make_week_figure 1.0
Swimlanes (work area) x day; one pill per merged task, coloured by worker; dashed pills = next steps."""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle

print('make_week_figure 1.0')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'week_2026-11-26')

SURF, INK, INK2, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8985', '#e6e5e1'
WORKER = {'DeepSeek': '#2a78d6', 'Gemini': '#eb6834', 'Claude (manager)': '#8a8985'}
plt.rcParams['font.family'] = ['Segoe UI', 'DejaVu Sans']

LANES = ['Activity model', '3D viewer', 'Smartwatch', 'Implant firmware', 'Studies & figures']
DAYS = ['Fri 20', 'Mon 23', 'Tue 24', 'Next']
# (lane, day, label, worker)  worker None = next step (dashed)
TASKS = [
    ('Activity model', 'Mon 23', 'G2  walker gait diagnosis', 'Gemini'),
    ('Activity model', 'Mon 23', 'A1  aid-gait data, rule C', 'DeepSeek'),
    ('Activity model', 'Mon 23', 'G3  synthetic-gap cause', 'Gemini'),
    ('Activity model', 'Tue 24', 'S1  stairs + ramps test', 'Gemini'),
    ('Activity model', 'Next', 'Walker / crutch recordings', None),
    ('3D viewer', 'Mon 23', 'V3  MuJoCo viewer, 50 motions', 'Gemini'),
    ('3D viewer', 'Mon 23', 'V3b  scenes + Blender', 'Gemini'),
    ('3D viewer', 'Mon 23', 'V3c/d  implant CAD, see-through', 'Gemini'),
    ('3D viewer', 'Mon 23', 'V3e  picker + Windows exe', 'Gemini'),
    ('3D viewer', 'Tue 24', 'Camera fix, own repo', 'Claude (manager)'),
    ('Smartwatch', 'Mon 23', 'G1  BLE code review', 'Gemini'),
    ('Smartwatch', 'Mon 23', 'W6  9 review fixes', 'DeepSeek'),
    ('Smartwatch', 'Tue 24', 'T1  home therapy mode', 'DeepSeek'),
    ('Smartwatch', 'Tue 24', 'T2  standing knee curl', 'DeepSeek'),
    ('Smartwatch', 'Next', 'Speaker + exercise test', None),
    ('Implant firmware', 'Tue 24', 'F1  3.2 kHz burst mode', 'DeepSeek'),
    ('Implant firmware', 'Next', 'Burst tap test, I2C soak', None),
    ('Studies & figures', 'Fri 20', 'V2  overview figure', 'DeepSeek'),
    ('Studies & figures', 'Mon 23', 'G0  Gemini joins', 'Gemini'),
    ('Studies & figures', 'Tue 24', 'L1  flexion + loosening', 'Gemini'),
    ('Studies & figures', 'Tue 24', 'R1  gait recovery score', 'Gemini'),
    ('Studies & figures', 'Tue 24', 'B1  burst design', 'Gemini'),
    ('Studies & figures', 'Next', 'Physio: targets, ±4°?', None),
]

# geometry (figure units = inches)
W, H = 16, 10.4
fig = plt.figure(figsize=(W, H), dpi=150, facecolor=SURF)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')

x_lane, x0, col_w = 0.55, 2.75, 3.25
pill_h, pill_gap = 0.34, 0.08
per_cell = {}
for t in TASKS:
    per_cell[(t[0], t[1])] = per_cell.get((t[0], t[1]), 0) + 1
lane_n = {l: max(per_cell.get((l, d), 0) for d in DAYS) for l in LANES}
lane_h = {l: lane_n[l] * (pill_h + pill_gap) + 0.28 for l in LANES}

# title + KPI strip
ax.text(x_lane, H - 0.55, 'KNEIL week at a glance', fontsize=24, fontweight='bold', color=INK, va='center')
ax.text(x_lane, H - 0.98, '20–26 Nov 2026 · two AI workers, one manager · every pill is a merged, reviewed task',
        fontsize=12.5, color=INK2, va='center')
kpis = [('20', 'tasks merged'), ('104', 'commits'), ('4', 'repos pushed'), ('4', 'decisions by you')]
for i, (v, lab) in enumerate(kpis):
    x = 9.0 + i * 1.75
    ax.text(x, H - 0.55, v, fontsize=24, fontweight='bold', color=INK, va='center')
    ax.text(x, H - 0.98, lab, fontsize=11, color=INK2, va='center')

# legend (worker identity)
lx, ly = x_lane, H - 1.5
for name, col in WORKER.items():
    ax.add_patch(Circle((lx + 0.08, ly), 0.08, color=col))
    ax.text(lx + 0.24, ly, name, fontsize=11, color=INK, va='center')
    lx += 0.55 + 0.085 * len(name)
ax.add_patch(FancyBboxPatch((lx, ly - 0.1), 0.34, 0.2, boxstyle='round,pad=0,rounding_size=0.08',
                            fc='none', ec=MUTED, lw=1.2, ls=(0, (3, 2))))
ax.text(lx + 0.46, ly, 'next step (not done yet)', fontsize=11, color=INK, va='center')

# day headers
y_top = H - 2.0
for j, d in enumerate(DAYS):
    xc = x0 + j * col_w
    ax.text(xc + 0.1, y_top, d, fontsize=13, fontweight='bold', color=INK if d != 'Next' else INK2, va='center')
y = y_top - 0.32

# lanes
for li, lane in enumerate(LANES):
    h = lane_h[lane]
    if li % 2 == 0:
        ax.add_patch(FancyBboxPatch((x_lane - 0.15, y - h), W - 2 * x_lane + 0.3, h,
                                    boxstyle='round,pad=0,rounding_size=0.08', fc='#f3f2ee', ec='none', zorder=0))
    ax.text(x_lane, y - 0.32, lane, fontsize=13, fontweight='bold', color=INK, va='center')
    for j, d in enumerate(DAYS):
        cell = [t for t in TASKS if t[0] == lane and t[1] == d]
        for k, (_, _, label, worker) in enumerate(cell):
            px = x0 + j * col_w
            py = y - 0.14 - (k + 1) * (pill_h + pill_gap) + pill_gap
            pw = col_w - 0.25
            if worker is None:
                ax.add_patch(FancyBboxPatch((px, py), pw, pill_h, boxstyle='round,pad=0,rounding_size=0.12',
                                            fc=SURF, ec=MUTED, lw=1.3, ls=(0, (4, 2.5)), zorder=2))
                ax.text(px + 0.16, py + pill_h / 2, label, fontsize=11, color=INK2, va='center', zorder=3)
            else:
                col = WORKER[worker]
                ax.add_patch(FancyBboxPatch((px, py), pw, pill_h, boxstyle='round,pad=0,rounding_size=0.12',
                                            fc=col, ec='none', alpha=0.16, zorder=2))
                ax.add_patch(Circle((px + 0.19, py + pill_h / 2), 0.075, color=col, zorder=3))
                ax.text(px + 0.36, py + pill_h / 2, label, fontsize=11, color=INK, va='center', zorder=3)
    y -= h + 0.12

# separator before "Next"
xs = x0 + 3 * col_w - 0.17
ax.plot([xs, xs], [y + 0.12, y_top + 0.2], color=GRID, lw=1.5, zorder=1)

ax.text(x_lane, 0.32, 'Source: merge commits in kneil_v4, kneil_smartwatch and kneil_firmware (git log), 20–26 Nov 2026. '
        'Decisions: label rule C, keep the implant CAD, keep V4 (no stairs + ramps), burst at 3.2 kHz / I2C 400 kHz.',
        fontsize=9.5, color=MUTED, va='center')
for ext in ('png', 'svg'):
    fig.savefig(f'{OUT}.{ext}', facecolor=SURF)
print('saved', OUT + '.png')
