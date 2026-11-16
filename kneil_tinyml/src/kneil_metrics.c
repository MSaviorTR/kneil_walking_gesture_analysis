#include <string.h>
#include "kneil_tinyml.h"

void kneil_metrics_reset(kneil_metrics_t *m)
{
	memset(m, 0, sizeof(*m));
	m->prev_class = -1;
	m->prev_stable = -1;
	m->run_class = -1;
}

static void account(kneil_metrics_t *m, int cls, float stride, float tilt, float peak)
{
	m->windows_by_class[cls]++;
	/* Sit/stand events: any run of transition windows (sit-to-stand or stand-to-sit, which the model can
	 * swap within one event) counts as one transition; its direction comes from the stable classes around
	 * it: sitting -> run -> standing/walking/stairs = sit-to-stand, standing/walking -> run -> sitting =
	 * stand-to-sit. Single misclassified windows without a consistent context do not count. */
	const int is_tr = (cls == KNEIL_SIT_TO_STAND || cls == KNEIL_STAND_TO_SIT);
	if (is_tr) {
		if (m->run_class < 0) { m->run_class = cls; m->run_len = 1; } else { m->run_len++; }
	} else {
		if (m->run_class >= 0) {
			const int upright = (cls == KNEIL_STANDING || cls == KNEIL_WALKING || cls == KNEIL_STAIRS_UP || cls == KNEIL_STAIRS_DOWN);
			if (m->prev_stable == KNEIL_SITTING && upright) { m->n_sit_to_stand++; m->sts_windows += (uint32_t)m->run_len; }
			else if ((m->prev_stable == KNEIL_STANDING || m->prev_stable == KNEIL_WALKING) && cls == KNEIL_SITTING) m->n_stand_to_sit++;
		}
		m->run_class = -1;
		m->prev_stable = cls;
	}
	if (cls == KNEIL_BED_TRANSFER && m->prev_class != cls) m->n_bed_transfer++;
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
	if (cls == KNEIL_SITTING) { m->sit_tilt_sum += tilt; m->sit_tilt_n++; }
	m->prev_class = cls;
}

void kneil_metrics_update(kneil_metrics_t *m, const kneil_classifier_t *c, int cls)
{
	if (cls < 0 || cls >= KNEIL_N_CLASSES) return;
	const float st = c->last_stride_s, ti = c->feat[KF_TILT_SAG_DEG], pk = c->feat[KF_MAX_M];
#if KNEIL_SMOOTH
	/* Majority of 3 consecutive windows: the middle window changes only if both neighbours agree on another
	 * class (isolated misclassifications and short flickers at transitions). One window of delay. */
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
	m->h_cls[1] = cls; m->h_stride[1] = st; m->h_tilt[1] = ti; m->h_peak[1] = pk;
#else
	account(m, cls, st, ti, pk);
#endif
}

static uint16_t u16(float v) { return (v <= 0.0f) ? 0 : (v >= 65535.0f) ? 65535 : (uint16_t)(v + 0.5f); }

void kneil_metrics_summary(const kneil_metrics_t *m, kneil_daily_summary_t *s)
{
	memset(s, 0, sizeof(*s));
	for (int k = 0; k < KNEIL_N_CLASSES; k++) s->minutes_by_class[k] = u16((float)m->windows_by_class[k] * KNEIL_HOP_S / 60.0f);
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
