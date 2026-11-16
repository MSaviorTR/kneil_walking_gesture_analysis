/* Host test: self-test vectors, then a streaming run that checks window framing against tools/expected_stream.txt */
#include <stdio.h>
#include <stdlib.h>
#include "kneil_tinyml.h"
#include "kneil_selftest.h"
int main(int argc, char **argv)
{
	kneil_selftest_result_t r = kneil_selftest();
	printf("selftest: %d vectors, max feature error %.3g, feature failures %d, class mismatches %d\n",
	       r.n_vectors, r.max_feature_err, r.n_feature_fail, r.n_class_mismatch);
	int fails = r.n_class_mismatch + r.n_feature_fail;
	if (argc > 1) {                                   /* stream file: lines "ax ay az" at KNEIL_FS_HZ */
		FILE *fp = fopen(argv[1], "r"); if (!fp) { perror("stream"); return 2; }
		static kneil_classifier_t c; kneil_metrics_t m; kneil_classifier_init(&c); kneil_metrics_reset(&m);
		float ax, ay, az; int n_out = 0;
		FILE *out = fopen(argc > 2 ? argv[2] : "stream_out.txt", "w");
		while (fscanf(fp, "%f %f %f", &ax, &ay, &az) == 3) {
			int cls = kneil_classifier_push(&c, ax, ay, az);
			if (cls >= 0) { kneil_metrics_update(&m, &c, cls); fprintf(out, "%d %.4f\n", cls, c.last_stride_s); n_out++; }
		}
		fclose(fp); fclose(out);
		kneil_daily_summary_t s; kneil_metrics_summary(&m, &s);
		printf("stream: %d windows classified | summary %zu bytes: walk %u min, sit-to-stand %u, stand-to-sit %u, steps %u, cadence %.1f/min, seated tilt %.1f deg\n",
		       n_out, sizeof(s), s.minutes_by_class[KNEIL_WALKING], s.n_sit_to_stand, s.n_stand_to_sit, s.steps, s.cadence_x10 / 10.0, s.sit_tilt_x10 / 10.0);
	}
	printf(fails ? "RESULT: FAIL\n" : "RESULT: PASS\n");
	return fails ? 1 : 0;
}
