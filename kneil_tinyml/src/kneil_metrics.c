#include <string.h>
#include "kneil_tinyml.h"

/* ------------------------------------------------------------------ events (rule R1)
 * A run of sit_to_stand / stand_to_sit windows (a single other window between two transition windows keeps the run
 * together) ends when 2 non-transition windows follow. It is counted when a still window lies within 3 windows before
 * the run, or within 3 windows after its end (so a count can come up to 3 windows late).
 * Direction = majority class of the run; a tie goes to the first window of the run.
 * bed_transfer uses the same run rule without the still condition.
 */
static void count_event(kneil_metrics_t *m, int first, int na, int nb, int len)
{
	const int dir = (na > nb) ? KNEIL_SIT_TO_STAND : (nb > na) ? KNEIL_STAND_TO_SIT : first;
	if (dir == KNEIL_SIT_TO_STAND) {
		m->n_sit_to_stand++;
		m->sts_windows += (uint32_t)len;
		m->posture = KNEIL_POSTURE_STANDING;
	} else {
		m->n_stand_to_sit++;
		m->posture = KNEIL_POSTURE_SITTING;
	}
}

static void close_run(kneil_metrics_t *m)
{
	if (m->run_still_before || m->run_still_after) {
		count_event(m, m->run_first, m->run_na, m->run_nb, m->run_len);
		return;
	}
	m->pending = 1;
	m->pending_until = m->run_last + 3;
	m->pending_first = m->run_first;
	m->pending_na = m->run_na;
	m->pending_nb = m->run_nb;
	m->pending_len = m->run_len;
}

/* ------------------------------------------------------------------ accounting
 * The class here is the one after the stairs rule and after the optional majority-of-3 smoothing (V3 behaviour).
 */
static void account(kneil_metrics_t *m, int cls, float stride, float tilt, float peak)
{
	m->windows_by_class[cls]++;
	if (cls == KNEIL_STILL) {
		if (m->posture == KNEIL_POSTURE_SITTING) m->windows_sitting++;
		else if (m->posture == KNEIL_POSTURE_STANDING) m->windows_standing++;
		else m->windows_still_unknown++;
	}
	if (cls == KNEIL_WALKING) {
		m->walk_peak_sum += peak; m->walk_peak_n++;
		if (stride > 0.0f) {
			const float cad = 120.0f / stride;
			m->cadence_sum += cad; m->cadence_n++; m->steps += cad / 60.0f * KNEIL_HOP_S;
		}
	} else if ((cls == KNEIL_STAIRS_UP || cls == KNEIL_STAIRS_DOWN) && stride > 0.0f) {
		const float cad = 120.0f / stride;
		m->stairs_cadence_sum += cad; m->stairs_cadence_n++; m->steps += cad / 60.0f * KNEIL_HOP_S;
	}
	if (cls == KNEIL_STILL && m->posture == KNEIL_POSTURE_SITTING) { m->sit_tilt_sum += tilt; m->sit_tilt_n++; }
}

/* One classified window: rule output -> events and posture (unsmoothed) -> smoothing -> minutes and counters. */
static void push_ruled(kneil_metrics_t *m, int cls, float stride, float tilt, float peak)
{
	if (cls < 0 || cls >= KNEIL_N_CLASSES) return;
	const int idx = m->idx;
	const int is_tr = (cls == KNEIL_SIT_TO_STAND || cls == KNEIL_STAND_TO_SIT);

	/* still bookkeeping first: "still within 3 windows before the run" must see a still at idx-1 .. idx-3 */
	if (cls == KNEIL_STILL) m->since_still = 0;
	else if (m->since_still >= 0) m->since_still++;

	/* a pending run: a still window up to 3 windows after the end of the run counts it */
	if (m->pending) {
		if (cls == KNEIL_STILL) {
			count_event(m, m->pending_first, m->pending_na, m->pending_nb, m->pending_len);
			m->pending = 0;
		} else if (idx >= m->pending_until) {
			m->pending = 0;
		}
	}
	/* a still window just after the last transition window of an open run (up to 3 windows, also inside the single
	 * window that keeps a run together) counts as evidence for that run */
	if (cls == KNEIL_STILL && m->run_len && idx > m->run_last && idx <= m->run_last + 3) m->run_still_after = 1;
	/* transition run */
	if (is_tr) {
		if (m->run_len == 0) {
			m->run_first = cls; m->run_na = 0; m->run_nb = 0; m->run_gap = 0;
			m->run_still_before = (m->since_still >= 1 && m->since_still <= 3);
			m->run_still_after = 0;
		}
		m->run_len++;
		if (cls == KNEIL_SIT_TO_STAND) m->run_na++; else m->run_nb++;
		m->run_last = idx;
		m->run_gap = 0;
	} else if (m->run_len) {
		m->run_gap++;
		if (m->run_gap >= 2) {
			close_run(m);
			m->run_len = 0;
		}
	}
	/* bed transfer run (no still condition) */
	if (cls == KNEIL_BED_TRANSFER) {
		m->bed_len++; m->bed_last = idx; m->bed_gap = 0;
	} else if (m->bed_len) {
		m->bed_gap++;
		if (m->bed_gap >= 2) {
			m->n_bed_transfer++;
			m->bed_len = 0;
			m->posture = KNEIL_POSTURE_UNKNOWN;
		}
	}
	/* posture from the plain class */
	if (cls == KNEIL_WALKING || cls == KNEIL_STAIRS_UP || cls == KNEIL_STAIRS_DOWN) m->posture = KNEIL_POSTURE_STANDING;
	else if (cls == KNEIL_LYING) m->posture = KNEIL_POSTURE_UNKNOWN;
	m->idx = idx + 1;
#if KNEIL_SMOOTH
	/* Majority of 3 consecutive windows: the middle window changes only if both neighbours agree on another class
	 * (isolated misclassifications and short flickers at transitions). One window of delay. */
	if (m->h_n == 2) {
		const int mid = (m->h_cls[0] == cls && m->h_cls[0] != m->h_cls[1]) ? m->h_cls[0] : m->h_cls[1];
		account(m, mid, m->h_stride[1], m->h_tilt[1], m->h_peak[1]);
		m->h_cls[0] = m->h_cls[1]; m->h_stride[0] = m->h_stride[1]; m->h_tilt[0] = m->h_tilt[1]; m->h_peak[0] = m->h_peak[1];
	} else if (m->h_n == 1) {                       /* the first window has no left neighbour: count it as it is */
		account(m, m->h_cls[1], m->h_stride[1], m->h_tilt[1], m->h_peak[1]);
		m->h_cls[0] = m->h_cls[1]; m->h_stride[0] = m->h_stride[1]; m->h_tilt[0] = m->h_tilt[1]; m->h_peak[0] = m->h_peak[1];
		m->h_n = 2;
	} else {
		m->h_n = 1;
	}
	m->h_cls[1] = cls; m->h_stride[1] = stride; m->h_tilt[1] = tilt; m->h_peak[1] = peak;
#else
	account(m, cls, stride, tilt, peak);
#endif
}

void kneil_metrics_reset(kneil_metrics_t *m)
{
	memset(m, 0, sizeof(*m));
	m->posture = KNEIL_POSTURE_UNKNOWN;
	m->since_still = -1;
}

void kneil_metrics_update(kneil_metrics_t *m, const kneil_classifier_t *c, int cls)
{
	push_ruled(m, cls, c->last_stride_s, c->feat[KF_TILT_SAG_DEG], c->feat[KF_MAX_M]);
}

void kneil_metrics_push(kneil_metrics_t *m, int raw_class, float vote, float stride, float tilt, float peak)
{
	push_ruled(m, kneil_stairs_rule(raw_class, vote), stride, tilt, peak);
}

static uint16_t u16(float v) { return (v <= 0.0f) ? 0 : (v >= 65535.0f) ? 65535 : (uint16_t)(v + 0.5f); }

static uint16_t minutes(uint32_t windows) { return u16((float)windows * KNEIL_HOP_S / 60.0f); }

void kneil_metrics_summary(const kneil_metrics_t *m, kneil_daily_summary_t *s)
{
	memset(s, 0, sizeof(*s));
	s->format = 2;
	s->n_classes = KNEIL_N_CLASSES;
	for (int k = 0; k < KNEIL_N_CLASSES; k++) s->minutes_by_class[k] = minutes(m->windows_by_class[k]);
	s->minutes_sitting = minutes(m->windows_sitting);
	s->minutes_standing = minutes(m->windows_standing);
	s->minutes_still_unknown = minutes(m->windows_still_unknown);
	s->n_sit_to_stand = m->n_sit_to_stand; s->n_stand_to_sit = m->n_stand_to_sit; s->n_bed_transfer = m->n_bed_transfer;
	s->sts_seconds_x10 = m->n_sit_to_stand ? u16(10.0f * (float)m->sts_windows * KNEIL_HOP_S / (float)m->n_sit_to_stand) : 0;
	s->steps = u16(m->steps);
	s->cadence_x10 = m->cadence_n ? u16(10.0f * m->cadence_sum / (float)m->cadence_n) : 0;
	s->stairs_cadence_x10 = m->stairs_cadence_n ? u16(10.0f * m->stairs_cadence_sum / (float)m->stairs_cadence_n) : 0;
	if (m->sit_tilt_n) {
		const float v = 10.0f * m->sit_tilt_sum / (float)m->sit_tilt_n;
		s->sit_tilt_x10 = (int16_t)((v > 32767.0f) ? 32767 : (v < -32768.0f) ? -32768 : (v >= 0 ? v + 0.5f : v - 0.5f));
	}
}
