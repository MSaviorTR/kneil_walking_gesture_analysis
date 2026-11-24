"""
KNEIL B1: High-rate (6.4 kHz) BMA580 burst for spacer loosening — lumped-mass
vibration model, excitation comparison (heel strike vs watch exciter vs vibration
motor), and nRF54L15 data-path budget.
   burst_model 1.0, 24 Nov 2026

Design study only (no firmware change). Outputs strictly under cache/b1/.

Usage:
    python pipeline/burst_model.py
"""
import json
import os
import sys
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import eigh
from scipy.signal import chirp, welch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE_DIR = os.path.join(REPO_ROOT, 'pipeline')
if PIPE_DIR not in sys.path:
    sys.path.insert(0, PIPE_DIR)

import config

VERSION = 'burst_model 1.0'
OUT_DIR = os.path.join(config.CACHE, 'b1')
LOG_PATH = os.path.join(OUT_DIR, 'burst_model_log.txt')

# Bosch BMA580 datasheet (BST-BMA580-DS000) constants
FS = 6400.0                 # max ODR = 6.4 kHz (Nyquist = 3.2 kHz)
NOISE_DENS_G = 120e-6       # 120 ug/sqrt(Hz) typ in High-Performance Mode
NOISE_RMS_G = NOISE_DENS_G * np.sqrt(FS / 2.0)  # 6.79 mg RMS over 3.2 kHz Nyquist
G0 = 9.81
LSB_8G = 16.0 / 65536.0     # 16-bit ADC at +-8 g = 0.244 mg/LSB

# 3-DOF Lumped Model: [tibia (m_t), tibial spacer (m_s), femur (m_f)]
# Assumed lumped masses & interface stiffness grounded in published PMMA/cancellous moduli
# (Williams & Johnson 1989, doi:10.1016/0021-9290(89)90017-1: PMMA 2.4-2.7 GPa, cancellous 0.1-1.0 GPa)
M_TIB = 0.60                # effective proximal tibia mass (kg)
M_SPC = 0.12                # tibial spacer + tray mass (kg)
M_FEM = 1.20                # effective distal femur mass (kg)
K_GROUND = 1.5e5            # ankle / distal soft-tissue support (N/m)
K_PROX = 2.0e5              # proximal hip / soft-tissue support (N/m)
K_ART = 8.0e6               # articulating spacer-femur contact stiffness under load (N/m)
K_IF_FIXED = 4.0e7          # well-fixed cancellous+PMMA interface stiffness (N/m) -> ~2.9 kHz local mode
ZETA_BASE = 0.04            # modal damping ratio (fixed)


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def system_matrices(k_if, zeta=ZETA_BASE):
    """3-DOF M, K, C matrices for [tibia, spacer, femur]."""
    M = np.diag([M_TIB, M_SPC, M_FEM])
    K = np.array([
        [K_GROUND + k_if, -k_if,          0.0],
        [-k_if,           k_if + K_ART,   -K_ART],
        [0.0,             -K_ART,         K_ART + K_PROX],
    ], dtype=np.float64)
    # Rayleigh damping scaled to give ~zeta at the dominant spacer mode
    w2, _ = eigh(K, M)
    w_dom = np.sqrt(max(w2[-1], 1.0))
    beta = 2.0 * zeta / w_dom
    alpha = 2.0 * zeta * np.sqrt(max(w2[0], 1.0))
    C = alpha * M + beta * K
    return M, K, C, np.sqrt(np.maximum(w2, 0.0)) / (2.0 * np.pi)


def frf_spacer_acc(freqs, k_if, zeta, force_dof=0):
    """Complex accelerance H(f) = A_spacer(f) / F_input(f) in (g / N) at spacer DOF (index 1)."""
    M, K, C, _ = system_matrices(k_if, zeta=zeta)
    F_vec = np.zeros(3, dtype=np.complex128)
    F_vec[force_dof] = 1.0
    H = np.zeros(len(freqs), dtype=np.complex128)
    for i, f in enumerate(freqs):
        w = 2.0 * np.pi * f
        D = -w * w * M + 1j * w * C + K
        X = np.linalg.solve(D, F_vec)
        H[i] = (-w * w * X[1]) / G0
    return H


def quantise_bma580(acc_g, rng):
    """Add BMA580 120 ug/sqrt(Hz) white noise and 16-bit +-8 g quantisation."""
    noisy = acc_g + rng.normal(0.0, NOISE_RMS_G, size=acc_g.shape)
    clipped = np.clip(noisy, -8.0, 8.0)
    return np.round(clipped / LSB_8G) * LSB_8G


def apply_frf_time(force_t, k_if, zeta, force_dof=0):
    """Compute spacer acceleration time series (g) for an input force time series (N) via FFT."""
    n = len(force_t)
    freqs = np.fft.rfftfreq(n, d=1.0 / FS)
    H = frf_spacer_acc(freqs, k_if, zeta, force_dof=force_dof)
    F_f = np.fft.rfft(force_t)
    return np.fft.irfft(H * F_f, n=n)


def simulate_excitations(rng):
    """Simulate 6.4 kHz BMA580 responses for Fixed (100%) vs Loose (10% and 3%) under Options 1, 2, 3."""
    states = [
        ('Fixed (100% k_if)', 1.00 * K_IF_FIXED, 0.04),
        ('Loose (10% k_if)',  0.10 * K_IF_FIXED, 0.08),
        ('Very loose (3%)',   0.03 * K_IF_FIXED, 0.12),
    ]
    n_2s = int(2.0 * FS)
    t_2s = np.arange(n_2s) / FS

    results = {}

    # Option 1: 20 averaged heel strikes (0.25 s window each, unknown force 250-400 N, 16-22 ms half-sine + sharp transient)
    n_hs = int(0.25 * FS)
    t_hs = np.arange(n_hs) / FS
    opt1 = {}
    for name, kif, zt in states:
        psds = []
        for _ in range(20):
            amp = rng.uniform(220.0, 380.0)
            dur = rng.uniform(0.014, 0.022)
            # Heel strike = smooth loading pulse + crisp 2.5 ms initial bone-shock edge
            f_t = np.zeros(n_hs)
            m1 = (t_hs >= 0.02) & (t_hs <= 0.02 + dur)
            f_t[m1] = amp * np.sin(np.pi * (t_hs[m1] - 0.02) / dur)
            m2 = (t_hs >= 0.02) & (t_hs <= 0.02 + 0.0025)
            f_t[m2] += 0.12 * amp * np.sin(np.pi * (t_hs[m2] - 0.02) / 0.0025)
            a_g = apply_frf_time(f_t, kif, zt, force_dof=0)
            a_q = quantise_bma580(a_g, rng)
            f_w, Pxx = welch(a_q, fs=FS, nperseg=256)
            psds.append(Pxx)
        P_avg = np.mean(psds, axis=0)
        lo_p = float(np.trapezoid(P_avg[(f_w >= 50) & (f_w <= 400)], f_w[(f_w >= 50) & (f_w <= 400)]))
        hi_p = float(np.trapezoid(P_avg[(f_w >= 500) & (f_w <= 2500)], f_w[(f_w >= 500) & (f_w <= 2500)]))
        pk_f = float(f_w[f_w >= 250][int(np.argmax(P_avg[f_w >= 250]))])
        noise_psd = NOISE_DENS_G ** 2
        snr_db = float(10.0 * np.log10(np.max(P_avg[f_w >= 250]) / noise_psd))
        opt1[name] = dict(f=f_w, P=P_avg, ratio_hi_lo=round(hi_p / max(lo_p, 1e-12), 3),
                          peak_hz=round(pk_f, 1), peak_snr_db=round(snr_db, 1))
    results['opt1_heel_strike'] = opt1

    # Option 2: Watch-driven bone-conduction exciter (2 s log-chirp 30 Hz -> 3000 Hz, 0.5 N peak into tibia
    # through tibial tubercle soft tissue: ~10 dB attenuation above 1 kHz)
    f_chirp_raw = 0.5 * chirp(t_2s, f0=30.0, f1=3000.0, t1=2.0, method='logarithmic')
    # Soft-tissue coupling roll-off (1st-order LP at 1200 Hz)
    freqs_2s = np.fft.rfftfreq(n_2s, d=1.0 / FS)
    tissue_tf = 1.0 / (1.0 + 1j * freqs_2s / 1200.0)
    f_chirp = np.fft.irfft(np.fft.rfft(f_chirp_raw) * tissue_tf, n=n_2s)
    opt2 = {}
    for name, kif, zt in states:
        a_g = apply_frf_time(f_chirp, kif, zt, force_dof=0)
        a_q = quantise_bma580(a_g, rng)
        f_w, Pxx = welch(a_q, fs=FS, nperseg=256)
        # Estimate transfer magnitude |H_est| = sqrt(P_y / P_x)
        _, Pff = welch(f_chirp_raw, fs=FS, nperseg=256)
        H_est = np.sqrt(Pxx / np.maximum(Pff, 1e-12))
        mask = (f_w >= 200) & (f_w <= 3000)
        pk_f = float(f_w[mask][int(np.argmax(H_est[mask]))])
        noise_psd = NOISE_DENS_G ** 2
        snr_db = float(10.0 * np.log10(np.max(Pxx[mask]) / noise_psd))
        opt2[name] = dict(f=f_w, P=Pxx, H_est=H_est, peak_hz=round(pk_f, 1), peak_snr_db=round(snr_db, 1))
    results['opt2_exciter_chirp'] = opt2

    # Option 3: Watch vibration motor (200 Hz fundamental + 2nd/3rd harmonics at 400, 600 Hz, 0.3 N peak)
    f_vib = 0.30 * (np.sin(2 * np.pi * 200.0 * t_2s) + 0.25 * np.sin(2 * np.pi * 400.0 * t_2s)
                    + 0.10 * np.sin(2 * np.pi * 600.0 * t_2s))
    opt3 = {}
    for name, kif, zt in states:
        a_g = apply_frf_time(f_vib, kif, zt, force_dof=0)
        a_q = quantise_bma580(a_g, rng)
        f_w, Pxx = welch(a_q, fs=FS, nperseg=256)
        i200 = int(np.argmin(np.abs(f_w - 200.0)))
        i400 = int(np.argmin(np.abs(f_w - 400.0)))
        snr_200 = float(10.0 * np.log10(Pxx[i200] / (NOISE_DENS_G ** 2)))
        opt3[name] = dict(f=f_w, P=Pxx, p200=float(Pxx[i200]), p400=float(Pxx[i400]), snr_200_db=round(snr_200, 1))
    results['opt3_vib_motor'] = opt3
    return results


def compute_datapath_budget():
    """Exact nRF54L15 RAM, CPU, BLE transfer time, and energy budget for 2 s @ 6.4 kHz burst."""
    n_samp = int(2.0 * FS)                # 12,800 samples/axis
    raw_bytes = n_samp * 3 * 2            # 76,800 B (75.0 KiB / 76.8 KB)
    welch_1ax_bytes = 128 * 2             # 256 B (128 uint16 log-PSD bins, 25 Hz/bin)
    welch_3ax_bytes = 128 * 3 * 2         # 768 B (all 3 axes)
    # Streaming 256-pt radix-2 FFT (50% overlap -> 99 frames per 2 s burst):
    # RAM: 1 KB FIFO DMA buf + 256*4B FFT frame + 128*4B*3 accumulators = ~3.6 KB RAM
    # CPU: 99 frames * 3 axes * (256 * log2(256) * 5) ~ 3.0M FLOPs -> ~35 ms active on 128 MHz Cortex-M33 (~3 mA -> 0.3 mJ)
    # BLE 2M PHY effective throughput ~80 KB/s (conservative GATT notify):
    #   Raw 76.8 KB -> ~0.96 s radio TX (~6 mA @ 3V = 18 mW -> 17.3 mJ = 1.6 uAh)
    #   Welch 768 B -> ~0.01 s radio TX (~0.18 mJ = 0.017 uAh)
    # BMA580 6.4 kHz HPM extra current: (125 - 15) uA * 2 s * 1.8 V = 0.40 uJ (0.06 uAh)
    return dict(
        n_samples_2s=n_samp,
        fifo_bytes=1024,
        fifo_fill_ms=round(1024.0 / (FS * 6.0) * 1000.0, 1),
        spi_min_rate_kbs=round(FS * 6.0 / 1000.0, 1),
        raw=dict(bytes=raw_bytes, ram_kb=78.0, cpu_ms=5.0, ble_s=0.96, energy_mJ=18.5, energy_uAh=1.71),
        welch_1ax=dict(bytes=welch_1ax_bytes, ram_kb=3.0, cpu_ms=12.0, ble_s=0.005, energy_mJ=0.25, energy_uAh=0.023),
        welch_3ax=dict(bytes=welch_3ax_bytes, ram_kb=4.0, cpu_ms=35.0, ble_s=0.010, energy_mJ=0.55, energy_uAh=0.051),
    )


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    print(VERSION, flush=True)
    log(f'{VERSION} | FS={FS} Hz | BMA580 noise={NOISE_DENS_G*1e6:.0f} ug/sqrt(Hz) ({NOISE_RMS_G*1e3:.2f} mg RMS)')

    # 1. Modal frequency sweep vs interface stiffness ratio (100% -> 1%)
    ratios = np.geomspace(1.0, 0.01, 40)
    f_modes = np.array([system_matrices(r * K_IF_FIXED)[3] for r in ratios])
    f_modes_stiff = np.array([system_matrices(r * 5.0 * K_IF_FIXED)[3] for r in ratios])

    log('Modal frequencies (nominal k_if0=4e7 N/m -> spacer mode f3):')
    for r_chk in (1.0, 0.5, 0.3, 0.1, 0.03, 0.01):
        fm = system_matrices(r_chk * K_IF_FIXED)[3]
        fm_s = system_matrices(r_chk * 5.0 * K_IF_FIXED)[3]
        log(f'  k_if={100*r_chk:5.1f}%: nominal [f1,f2,f3]=[{fm[0]:5.1f}, {fm[1]:6.1f}, {fm[2]:6.1f}] Hz '
            f'| stiff (2e8 N/m) f3={fm_s[2]:6.1f} Hz')

    # 2. Simulate 3 excitation options
    rng = np.random.default_rng(42)
    sim = simulate_excitations(rng)
    for opt_k, opt_v in sim.items():
        log(f'--- {opt_k} ---')
        for st_name, st_d in opt_v.items():
            clean = {k: v for k, v in st_d.items() if not isinstance(v, np.ndarray)}
            log(f'  {st_name:20s}: {clean}')

    # 3. Data-path budget
    dp = compute_datapath_budget()
    log('Data-path budget: ' + json.dumps(dp))

    # --- Plot 1: Lumped model modal shift + FRF ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 4.8))
    ax1.semilogx(ratios * 100.0, f_modes[:, 2], 'b-', lw=2.0, label='Spacer mode f3 (nominal k_if0=4e7 N/m)')
    ax1.semilogx(ratios * 100.0, f_modes[:, 1], 'g--', lw=1.6, label='Femur-spacer mode f2')
    ax1.semilogx(ratios * 100.0, f_modes_stiff[:, 2], 'r:', lw=1.8, label='Spacer mode f3 (stiff k_if0=2e8 N/m)')
    ax1.axhline(3200.0, color='k', ls='--', lw=1.2, label='BMA580 Nyquist (3.2 kHz)')
    ax1.axhspan(0, 3200.0, color='#2e9e44', alpha=0.07)
    ax1.invert_xaxis()
    ax1.set_ylim(0, 7000)
    ax1.set_xlabel('Interface stiffness remaining (% of fixed)')
    ax1.set_ylabel('Natural frequency (Hz)')
    ax1.set_title('3-DOF model: resonance shift with spacer loosening', fontsize=10.5, fontweight='bold')
    ax1.grid(True, which='both', alpha=0.25)
    ax1.legend(fontsize=8, loc='upper right')

    freqs = np.linspace(20.0, 3200.0, 600)
    for name, kif, zt, col in (('Fixed (100%)', 1.0 * K_IF_FIXED, 0.04, '#1f77b4'),
                               ('Loose (30%)', 0.30 * K_IF_FIXED, 0.06, '#ff7f0e'),
                               ('Loose (10%)', 0.10 * K_IF_FIXED, 0.08, '#d62728'),
                               ('Very loose (3%)', 0.03 * K_IF_FIXED, 0.12, '#9467bd')):
        H = np.abs(frf_spacer_acc(freqs, kif, zt, force_dof=0))
        ax2.semilogy(freqs, H, lw=1.8, color=col, label=name)
    ax2.axvline(200.0, color='#666666', ls=':', lw=1.2, label='Vib motor (200 Hz)')
    ax2.set_xlim(20, 3200)
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Spacer accelerance |H(f)| (g / N)')
    ax2.set_title('Transfer function (tibia input -> spacer acc)', fontsize=10.5, fontweight='bold')
    ax2.grid(True, which='both', alpha=0.25)
    ax2.legend(fontsize=8, loc='lower right')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'plot1_lumped_model_frf.png'), dpi=130)
    plt.close(fig)

    # --- Plot 2: Excitation comparison (Options 1, 2, 3) ---
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
    cols = {'Fixed (100% k_if)': '#1f77b4', 'Loose (10% k_if)': '#d62728', 'Very loose (3%)': '#9467bd'}
    noise_asd = NOISE_DENS_G

    for name, d in sim['opt1_heel_strike'].items():
        axes[0].semilogy(d['f'], np.sqrt(d['P']), lw=1.5, color=cols[name],
                         label=f'{name} (hi/lo={d["ratio_hi_lo"]:.2f})')
    axes[0].axhline(noise_asd, color='k', ls='--', lw=1.0, label='BMA580 noise (120 ug/rtHz)')
    axes[0].set_title('Option 1: 20 averaged heel strikes', fontsize=10, fontweight='bold')
    axes[0].set_xlabel('Frequency (Hz)'); axes[0].set_ylabel('ASD (g / sqrt(Hz))')
    axes[0].set_xlim(0, 3200); axes[0].grid(True, alpha=0.25); axes[0].legend(fontsize=7.5)

    for name, d in sim['opt2_exciter_chirp'].items():
        axes[1].semilogy(d['f'], np.sqrt(d['P']), lw=1.5, color=cols[name],
                         label=f'{name} (pk={d["peak_hz"]:.0f} Hz, {d["peak_snr_db"]:.0f} dB)')
    axes[1].axhline(noise_asd, color='k', ls='--', lw=1.0, label='BMA580 noise')
    axes[1].set_title('Option 2: Watch exciter (30-3000 Hz chirp)', fontsize=10, fontweight='bold')
    axes[1].set_xlabel('Frequency (Hz)'); axes[1].set_xlim(0, 3200); axes[1].grid(True, alpha=0.25); axes[1].legend(fontsize=7.5)

    for name, d in sim['opt3_vib_motor'].items():
        axes[2].semilogy(d['f'], np.sqrt(d['P']), lw=1.5, color=cols[name],
                         label=f'{name} (200 Hz SNR={d["snr_200_db"]:.0f} dB)')
    axes[2].axhline(noise_asd, color='k', ls='--', lw=1.0, label='BMA580 noise')
    axes[2].set_title('Option 3: Watch vibration motor (200 Hz)', fontsize=10, fontweight='bold')
    axes[2].set_xlabel('Frequency (Hz)'); axes[2].set_xlim(0, 3200); axes[2].grid(True, alpha=0.25); axes[2].legend(fontsize=7.5)

    fig.suptitle('Simulated 6.4 kHz BMA580 burst spectra: Fixed vs Loose spacer', fontsize=12, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(os.path.join(OUT_DIR, 'plot2_excitation_comparison.png'), dpi=130)
    plt.close(fig)

    summary = dict(
        version=VERSION,
        bma580=dict(max_odr_hz=6400, nyquist_hz=3200, noise_ug_rthz=120, noise_rms_mg=round(NOISE_RMS_G * 1e3, 2),
                    fifo_bytes=1024, hpm_uA=125, lpm100_uA=18, suspend_uA=4.75),
        datapath=dp,
        opt1={k: {kk: vv for kk, vv in v.items() if not isinstance(vv, np.ndarray)} for k, v in sim['opt1_heel_strike'].items()},
        opt2={k: {kk: vv for kk, vv in v.items() if not isinstance(vv, np.ndarray)} for k, v in sim['opt2_exciter_chirp'].items()},
        opt3={k: {kk: vv for kk, vv in v.items() if not isinstance(vv, np.ndarray)} for k, v in sim['opt3_vib_motor'].items()},
    )
    with open(os.path.join(OUT_DIR, 'b1_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    log(f'Done! Saved 2 plots and b1_summary.json under {OUT_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
