/* Host test: self-test vectors, then a streaming run that writes the raw class, the vote share and the class after
 * the stairs rule of every window (and the daily summary) so a Python check can compare them. */
#include <stdio.h>
#include <stdlib.h>
#include "kneil_tinyml.h"
#include "kneil_selftest.h"

int main(int argc, char **argv)
{
	kneil_selftest_result_t r = kneil_selftest();
	printf("selftest: %d vectors, max feature error %.3g, feature failures %d, class mismatches %d\n",
	       r.n_vectors, r.max_feature_err, r.n_feature_fail, r.n_class_mismatch);
	printf("library %s: window %d samples (%.0f s), hop %d samples, %d classes, stairs vote %.2f\n",
	       KNEIL_LIB_VERSION, (int)KNEIL_WIN_N, (double)KNEIL_WIN_N / (double)KNEIL_FS_HZ, (int)KNEIL_HOP_N,
	       KNEIL_N_CLASSES, (double)KNEIL_MODEL_STAIRS_MIN_VOTE);
	printf("sizes: classifier %zu bytes, metrics %zu bytes, summary %zu bytes\n",
	       sizeof(kneil_classifier_t), sizeof(kneil_metrics_t), sizeof(kneil_daily_summary_t));
	int fails = r.n_class_mismatch + r.n_feature_fail;
	if (argc > 1) {                                   /* stream file: lines "ax ay az" at KNEIL_FS_HZ */
		FILE *fp = fopen(argv[1], "r"); if (!fp) { perror("stream"); return 2; }
		static kneil_classifier_t c; kneil_metrics_t m; kneil_classifier_init(&c); kneil_metrics_reset(&m);
		float ax, ay, az; int n_out = 0;
		FILE *out = fopen(argc > 2 ? argv[2] : "stream_out.txt", "w");
		if (!out) { perror("out"); fclose(fp); return 2; }
		fprintf(out, "# raw vote class stride\n");
		while (fscanf(fp, "%f %f %f", &ax, &ay, &az) == 3) {
			int cls = kneil_classifier_push(&c, ax, ay, az);
			if (cls >= 0) { kneil_metrics_update(&m, &c, cls); fprintf(out, "%d %.4f %d %.4f\n", c.raw_class, (double)c.vote, cls, (double)c.last_stride_s); n_out++; }
		}
		fclose(fp); fclose(out);
		kneil_daily_summary_t s; kneil_metrics_summary(&m, &s);
		printf("stream: %d windows classified | summary %zu bytes (format %u, %u classes): walk %u min, still %u "
		       "(sit %u / stand %u / unknown %u) min, lying %u min, stairs up/down %u/%u min, sit-to-stand %u, "
		       "stand-to-sit %u, bed transfer %u, steps %u, cadence %.1f/min, stairs cadence %.1f/min, seated tilt %.1f deg\n",
		       n_out, sizeof(s), (unsigned)s.format, (unsigned)s.n_classes,
		       s.minutes_by_class[KNEIL_WALKING], s.minutes_by_class[KNEIL_STILL], s.minutes_sitting,
		       s.minutes_standing, s.minutes_still_unknown, s.minutes_by_class[KNEIL_LYING],
		       s.minutes_by_class[KNEIL_STAIRS_UP], s.minutes_by_class[KNEIL_STAIRS_DOWN],
		       s.n_sit_to_stand, s.n_stand_to_sit, s.n_bed_transfer, s.steps,
		       s.cadence_x10 / 10.0, s.stairs_cadence_x10 / 10.0, s.sit_tilt_x10 / 10.0);
	}
	printf(fails ? "RESULT: FAIL\n" : "RESULT: PASS\n");
	return fails ? 1 : 0;
}
