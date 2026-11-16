#include <math.h>
#include "kneil_tinyml.h"

#define RAD2DEG 57.29577951f

static inline float mag3(float x, float y, float z) { return sqrtf(x * x + y * y + z * z); }

void kneil_features(const float *x, const float *y, const float *z, int n, float fs, float *f)
{
	float sx = 0, sy = 0, sz = 0, sm = 0, mmin = 1e9f, mmax = -1e9f;
	for (int i = 0; i < n; i++) {
		float m = mag3(x[i], y[i], z[i]);
		sx += x[i]; sy += y[i]; sz += z[i]; sm += m;
		if (m < mmin) mmin = m;
		if (m > mmax) mmax = m;
	}
	const float inv_n = 1.0f / (float)n;
	const float mx = sx * inv_n, my = sy * inv_n, mz = sz * inv_n, mm = sm * inv_n;
	const int l1 = (int)(0.5f * fs + 0.5f), l2 = (int)(1.0f * fs + 0.5f), q = n / 4;
	float vx = 0, vy = 0, vz = 0, vm = 0, cxz = 0, jerk = 0, d2 = 0, ac1 = 0, ac2 = 0;
	float tx0 = 0, tx1 = 0, tz0 = 0, tz1 = 0, mprev = 0, dzprev = 0;
	int zc = 0;
	for (int i = 0; i < n; i++) {
		const float m = mag3(x[i], y[i], z[i]);
		const float dx = x[i] - mx, dy = y[i] - my, dz = z[i] - mz, dm = m - mm;
		vx += dx * dx; vy += dy * dy; vz += dz * dz; vm += dm * dm; cxz += dx * dz;
		if (i > 0) {
			const float dd = m - mprev;
			jerk += fabsf(dd); d2 += dd * dd;
			if ((dz > 0.0f) != (dzprev > 0.0f)) zc++;
		}
		if (i >= l1) ac1 += dm * (mag3(x[i - l1], y[i - l1], z[i - l1]) - mm);
		if (i >= l2) ac2 += dm * (mag3(x[i - l2], y[i - l2], z[i - l2]) - mm);
		if (i < q) { tx0 += x[i]; tz0 += z[i]; }
		if (i >= n - q) { tx1 += x[i]; tz1 += z[i]; }
		mprev = m; dzprev = dz;
	}
	const float eps = 1e-9f;
	f[KF_MEAN_X] = mx; f[KF_MEAN_Y] = my; f[KF_MEAN_Z] = mz;
	f[KF_STD_X] = sqrtf(vx * inv_n); f[KF_STD_Y] = sqrtf(vy * inv_n); f[KF_STD_Z] = sqrtf(vz * inv_n);
	f[KF_STD_M] = sqrtf(vm * inv_n); f[KF_MEAN_M] = mm; f[KF_PTP_M] = mmax - mmin; f[KF_MAX_M] = mmax;
	f[KF_JERK_M] = jerk / (float)(n - 1) * fs;
	f[KF_TILT_SAG_DEG] = atan2f(-mx, mz) * RAD2DEG;
	f[KF_TILT_COR_DEG] = atan2f(my, mz) * RAD2DEG;
	f[KF_AC_M_05S] = ac1 / (vm + eps);
	f[KF_AC_M_10S] = ac2 / (vm + eps);
	f[KF_ZCR_Z_HZ] = (float)zc * fs / (float)n;
	f[KF_TREND_X] = (tx1 - tx0) / (float)q;
	f[KF_TREND_Z] = (tz1 - tz0) / (float)q;
	f[KF_CORR_XZ] = cxz / sqrtf(vx * vz + eps);
	f[KF_HF_RATIO] = d2 / (vm + eps);
}

float kneil_stride_period(const float *m, int n, float fs)
{
	if (n < (int)(2.5f * fs)) return 0.0f;
	float mean = 0;
	for (int i = 0; i < n; i++) mean += m[i];
	mean /= (float)n;
	float var = 0;
	for (int i = 0; i < n; i++) var += (m[i] - mean) * (m[i] - mean);
	if (var < 1e-6f) return 0.0f;
	const int lo = (int)(0.6f * fs), hi = (int)(1.8f * fs);
	float best = -1.0f, r_prev = 0, r_best_prev = 0, r_best_next = 0;
	int best_l = 0;
	float r_l[2] = {0, 0};
	for (int l = lo; l <= hi && l < n - 1; l++) {
		float acc = 0;
		for (int i = l; i < n; i++) acc += (m[i] - mean) * (m[i - l] - mean);
		const float r = acc / var * (float)n / (float)(n - l);
		if (r > best) { best = r; best_l = l; r_best_prev = r_prev; }
		if (l == best_l + 1) r_best_next = r;
		r_prev = r; (void)r_l;
	}
	if (best < 0.3f || best_l <= lo || best_l >= hi) return 0.0f;
	/* parabolic interpolation around the peak */
	const float den = r_best_prev - 2.0f * best + r_best_next;
	const float off = (fabsf(den) > 1e-9f) ? 0.5f * (r_best_prev - r_best_next) / den : 0.0f;
	return ((float)best_l + off) / fs;
}


void kneil_lowpass_design(kneil_biquad_t *f, float fs, float fc)
{
	const float K = tanf(3.14159265f * fc / fs), r2 = 1.41421356f;
	const float norm = 1.0f / (1.0f + r2 * K + K * K);
	f->b0 = K * K * norm; f->b1 = 2.0f * f->b0; f->b2 = f->b0;
	f->a1 = 2.0f * (K * K - 1.0f) * norm; f->a2 = (1.0f - r2 * K + K * K) * norm;
	f->z1 = f->z2 = 0.0f; f->primed = 0;
}

float kneil_lowpass_step(kneil_biquad_t *f, float x)
{
	if (!f->primed) {                                   /* steady state for a constant input x */
		f->z1 = x * (f->b1 + f->b2 - f->a1 - f->a2); f->z2 = x * (f->b2 - f->a2); f->primed = 1;
	}
	const float y = f->b0 * x + f->z1;
	f->z1 = f->b1 * x - f->a1 * y + f->z2;
	f->z2 = f->b2 * x - f->a2 * y;
	return y;
}
