#include <math.h>
#include "kneil_tinyml.h"
#include "kneil_selftest.h"
#include "../tests/kneil_test_vectors.h"

int32_t kneil_model_predict(const float *features, int32_t features_length);

kneil_selftest_result_t kneil_selftest(void)
{
	kneil_selftest_result_t r = {KNEIL_TV_N, 0.0f, 0, 0};
	static float x[KNEIL_WIN_N], y[KNEIL_WIN_N], z[KNEIL_WIN_N];
	float f[KNEIL_N_FEATURES];
	for (int v = 0; v < KNEIL_TV_N; v++) {
		for (int i = 0; i < KNEIL_WIN_N; i++) { x[i] = kneil_tv_raw[v][i][0]; y[i] = kneil_tv_raw[v][i][1]; z[i] = kneil_tv_raw[v][i][2]; }
		kneil_features(x, y, z, KNEIL_WIN_N, (float)KNEIL_FS_HZ, f);
		int fail = 0;
		for (int k = 0; k < KNEIL_N_FEATURES; k++) {
			const float e = fabsf(f[k] - kneil_tv_feat[v][k]);
			if (e > r.max_feature_err) r.max_feature_err = e;
			if (e > 1e-5f && e > 1e-3f * fabsf(kneil_tv_feat[v][k])) fail = 1;
		}
		r.n_feature_fail += fail;
#if defined(KNEIL_MODEL_SMALL) || defined(CONFIG_KNEIL_TINYML_MODEL_SMALL)
		const int expected = kneil_tv_class_tree[v];
#else
		const int expected = kneil_tv_class_forest[v];
#endif
		if ((int)kneil_model_predict(kneil_tv_feat[v], KNEIL_N_FEATURES) != expected) r.n_class_mismatch++;
	}
	return r;
}
