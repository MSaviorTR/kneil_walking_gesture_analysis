"""
Python twin of the kneil_tinyml v2.0 metrics, for the PC app and for the checks.   metrics_ref 1.0, 17 Nov 2026

Same order per window as src/kneil_metrics.c: stairs rule -> transition events (rule R1, unsmoothed) and posture ->
majority-of-3 smoothing -> minutes and the other counters. Produces the 40-byte daily summary format 2 (packed,
little-endian), byte-identical to the C library on the same input.

Usage:
    m = Metrics()                       # stairs_min_vote from the model header, smooth=True
    for raw, vote in stream: m.push(raw, vote)      # stride/tilt/peak optional (0 = not known)
    buf = m.summary_bytes(); s = decode(buf)
"""
import struct

import numpy as np

VERSION = 'metrics_ref 1.0'
WALKING, STAIRS_UP, STAIRS_DOWN, STILL, LYING, SIT_TO_STAND, STAND_TO_SIT, BED_TRANSFER = range(8)
N_CLASSES = 8
UNKNOWN, SITTING, STANDING = 0, 1, 2
CLASSES = ['walking', 'stairs_up', 'stairs_down', 'still', 'lying', 'sit_to_stand', 'stand_to_sit', 'bed_transfer']
FORMAT = 2


def stairs_rule(raw_class, vote, min_vote=0.60):
    """kneil_stairs_rule(): stairs survive only with a large enough vote share, everything else is unchanged."""
    if raw_class in (STAIRS_UP, STAIRS_DOWN) and vote < min_vote:
        return WALKING
    return raw_class


def _u16(v):
    """Same rounding as u16() in C: 0 below zero, truncate(v + 0.5)."""
    if v <= 0.0:
        return 0
    if v >= 65535.0:
        return 65535
    return int(np.float32(v) + np.float32(0.5))


def _i16(v):
    if v > 32767.0:
        return 32767
    if v < -32768.0:
        return -32768
    return int(np.float32(v) + np.float32(0.5)) if v >= 0 else int(np.float32(v) - np.float32(0.5))


class Metrics:
    """State machine of kneil_metrics_t (v2.0)."""

    def __init__(self, stairs_min_vote=0.60, smooth=True, hop_s=1.0):
        self.min_vote = float(np.float32(stairs_min_vote))
        self.smooth = bool(smooth)
        self.hop_s = float(np.float32(hop_s))
        self.reset()

    def reset(self):
        self.windows = [0] * N_CLASSES
        self.w_sitting = self.w_standing = self.w_still_unknown = 0
        self.n_sts = self.n_s2s = self.n_bed = 0
        self.sts_windows = 0
        self.cadence_sum = np.float32(0.0); self.cadence_n = 0
        self.stairs_cadence_sum = np.float32(0.0); self.stairs_cadence_n = 0
        self.sit_tilt_sum = np.float32(0.0); self.sit_tilt_n = 0
        self.walk_peak_sum = np.float32(0.0); self.walk_peak_n = 0
        self.steps = np.float32(0.0)
        self.posture = UNKNOWN
        self.idx = 0
        self.since_still = -1
        self.run_len = 0; self.run_first = 0; self.run_na = 0; self.run_nb = 0
        self.run_gap = 0; self.run_last = 0; self.run_still_before = 0; self.run_still_after = 0
        self.pending = 0; self.pending_until = 0; self.pending_first = 0
        self.pending_na = 0; self.pending_nb = 0; self.pending_len = 0
        self.bed_len = 0; self.bed_gap = 0; self.bed_last = 0
        self.h_n = 0
        self.h = [None, None]          # (cls, stride, tilt, peak) of the last two windows

    # ------------------------------------------------------------------ events
    def _count_event(self, first, na, nb, length):
        direction = SIT_TO_STAND if na > nb else STAND_TO_SIT if nb > na else first
        if direction == SIT_TO_STAND:
            self.n_sts += 1
            self.sts_windows += length
            self.posture = STANDING
        else:
            self.n_s2s += 1
            self.posture = SITTING

    def _close_run(self):
        if self.run_still_before or self.run_still_after:
            self._count_event(self.run_first, self.run_na, self.run_nb, self.run_len)
            return
        self.pending = 1
        self.pending_until = self.run_last + 3
        self.pending_first = self.run_first
        self.pending_na = self.run_na
        self.pending_nb = self.run_nb
        self.pending_len = self.run_len

    # ------------------------------------------------------------------ accounting
    def _account(self, cls, stride, tilt, peak):
        self.windows[cls] += 1
        if cls == STILL:
            if self.posture == SITTING:
                self.w_sitting += 1
            elif self.posture == STANDING:
                self.w_standing += 1
            else:
                self.w_still_unknown += 1
        if cls == WALKING:
            self.walk_peak_sum = np.float32(self.walk_peak_sum + np.float32(peak)); self.walk_peak_n += 1
            if stride > 0.0:
                cad = np.float32(120.0) / np.float32(stride)
                self.cadence_sum = np.float32(self.cadence_sum + cad); self.cadence_n += 1
                self.steps = np.float32(self.steps + np.float32(cad / np.float32(60.0)) * np.float32(self.hop_s))
        elif cls in (STAIRS_UP, STAIRS_DOWN) and stride > 0.0:
            cad = np.float32(120.0) / np.float32(stride)
            self.stairs_cadence_sum = np.float32(self.stairs_cadence_sum + cad); self.stairs_cadence_n += 1
            self.steps = np.float32(self.steps + np.float32(cad / np.float32(60.0)) * np.float32(self.hop_s))
        if cls == STILL and self.posture == SITTING:
            self.sit_tilt_sum = np.float32(self.sit_tilt_sum + np.float32(tilt)); self.sit_tilt_n += 1

    def _push_ruled(self, cls, stride, tilt, peak):
        if cls < 0 or cls >= N_CLASSES:
            return
        idx = self.idx
        # still bookkeeping first: "still within 3 windows before the run" must see a still at idx-1 .. idx-3
        if cls == STILL:
            self.since_still = 0
        elif self.since_still >= 0:
            self.since_still += 1
        # a pending run: a still window up to 3 windows after the end of the run counts it
        if self.pending:
            if cls == STILL:
                self._count_event(self.pending_first, self.pending_na, self.pending_nb, self.pending_len)
                self.pending = 0
            elif idx >= self.pending_until:
                self.pending = 0
        # a still window just after the last transition window of an open run counts as evidence for that run
        if cls == STILL and self.run_len and idx > self.run_last and idx <= self.run_last + 3:
            self.run_still_after = 1
        # transition run
        if cls in (SIT_TO_STAND, STAND_TO_SIT):
            if self.run_len == 0:
                self.run_first = cls; self.run_na = 0; self.run_nb = 0; self.run_gap = 0
                self.run_still_before = 1 if 1 <= self.since_still <= 3 else 0
                self.run_still_after = 0
            self.run_len += 1
            if cls == SIT_TO_STAND:
                self.run_na += 1
            else:
                self.run_nb += 1
            self.run_last = idx
            self.run_gap = 0
        elif self.run_len:
            self.run_gap += 1
            if self.run_gap >= 2:
                self._close_run()
                self.run_len = 0
        # bed transfer run (no still condition)
        if cls == BED_TRANSFER:
            self.bed_len += 1; self.bed_last = idx; self.bed_gap = 0
        elif self.bed_len:
            self.bed_gap += 1
            if self.bed_gap >= 2:
                self.n_bed += 1
                self.bed_len = 0
                self.posture = UNKNOWN
        # posture from the plain class
        if cls in (WALKING, STAIRS_UP, STAIRS_DOWN):
            self.posture = STANDING
        elif cls == LYING:
            self.posture = UNKNOWN
        self.idx = idx + 1
        # majority of 3 (same as C)
        if self.smooth:
            if self.h_n == 2:
                c0, s0, t0, p0 = self.h[0]
                c1, s1, t1, p1 = self.h[1]
                mid = c0 if (c0 == cls and c0 != c1) else c1
                self._account(mid, s1, t1, p1)
                self.h[0] = self.h[1]
            elif self.h_n == 1:
                c1, s1, t1, p1 = self.h[1]
                self._account(c1, s1, t1, p1)
                self.h[0] = self.h[1]
                self.h_n = 2
            else:
                self.h_n = 1
            self.h[1] = (cls, stride, tilt, peak)
        else:
            self._account(cls, stride, tilt, peak)

    def push(self, raw_class, vote, stride=0.0, tilt=0.0, peak=0.0):
        """One window: raw class + vote share (stair rule applied here, like kneil_metrics_push)."""
        self._push_ruled(stairs_rule(raw_class, vote, self.min_vote), stride, tilt, peak)

    def push_ruled(self, cls, stride=0.0, tilt=0.0, peak=0.0):
        """One window whose class is already after the rule (what kneil_metrics_update does)."""
        self._push_ruled(cls, stride, tilt, peak)

    # ------------------------------------------------------------------ summary
    def summary(self):
        hop = self.hop_s
        d = dict(format=FORMAT, n_classes=N_CLASSES,
                 minutes_by_class=[_u16(np.float32(w) * np.float32(hop) / np.float32(60.0)) for w in self.windows],
                 minutes_sitting=_u16(np.float32(self.w_sitting) * np.float32(hop) / np.float32(60.0)),
                 minutes_standing=_u16(np.float32(self.w_standing) * np.float32(hop) / np.float32(60.0)),
                 minutes_still_unknown=_u16(np.float32(self.w_still_unknown) * np.float32(hop) / np.float32(60.0)),
                 n_sit_to_stand=self.n_sts, n_stand_to_sit=self.n_s2s, n_bed_transfer=self.n_bed,
                 sts_seconds_x10=(_u16(np.float32(10.0) * np.float32(self.sts_windows) * np.float32(hop)
                                       / np.float32(self.n_sts)) if self.n_sts else 0),
                 steps=_u16(self.steps),
                 cadence_x10=(_u16(np.float32(10.0) * self.cadence_sum / np.float32(self.cadence_n))
                              if self.cadence_n else 0),
                 stairs_cadence_x10=(_u16(np.float32(10.0) * self.stairs_cadence_sum / np.float32(self.stairs_cadence_n))
                                     if self.stairs_cadence_n else 0),
                 sit_tilt_x10=(_i16(np.float32(10.0) * self.sit_tilt_sum / np.float32(self.sit_tilt_n))
                               if self.sit_tilt_n else 0))
        return d

    def summary_bytes(self):
        """The packed 40-byte struct, little-endian (same layout as kneil_daily_summary_t)."""
        d = self.summary()
        return struct.pack('<BB8H3H3H4Hh', d['format'], d['n_classes'], *d['minutes_by_class'],
                           d['minutes_sitting'], d['minutes_standing'], d['minutes_still_unknown'],
                           d['n_sit_to_stand'], d['n_stand_to_sit'], d['n_bed_transfer'],
                           d['sts_seconds_x10'], d['steps'], d['cadence_x10'], d['stairs_cadence_x10'],
                           d['sit_tilt_x10'])


FIELDS = ['format', 'n_classes', 'minutes_by_class', 'minutes_sitting', 'minutes_standing', 'minutes_still_unknown',
          'n_sit_to_stand', 'n_stand_to_sit', 'n_bed_transfer', 'sts_seconds_x10', 'steps', 'cadence_x10',
          'stairs_cadence_x10', 'sit_tilt_x10']


def decode(buf):
    """Decode the 40-byte summary (bytes) into a dict with names."""
    v = struct.unpack('<BB8H3H3H4Hh', bytes(buf))
    d = dict(zip(['format', 'n_classes'], v[:2]))
    d['minutes_by_class'] = list(v[2:10])
    d['minutes_sitting'], d['minutes_standing'], d['minutes_still_unknown'] = v[10:13]
    d['n_sit_to_stand'], d['n_stand_to_sit'], d['n_bed_transfer'] = v[13:16]
    d['sts_seconds_x10'], d['steps'], d['cadence_x10'], d['stairs_cadence_x10'] = v[16:20]
    d['sit_tilt_x10'] = v[20]
    return d
