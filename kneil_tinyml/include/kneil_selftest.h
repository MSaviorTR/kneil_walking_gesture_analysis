#ifndef KNEIL_SELFTEST_H
#define KNEIL_SELFTEST_H
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { int n_vectors; float max_feature_err; int n_class_mismatch; int n_feature_fail; } kneil_selftest_result_t;
/* Runs the embedded test vectors through kneil_features() and the model. Pass: n_class_mismatch == 0
 * and n_feature_fail == 0 (relative tolerance 1e-3 on each feature, absolute 1e-5 near zero). */
kneil_selftest_result_t kneil_selftest(void);
#ifdef __cplusplus
}
#endif
#endif
