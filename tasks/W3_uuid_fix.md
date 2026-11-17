# Task W3: wrong KNEIL service UUID on the watch (found on hardware, 17 Nov 2026)

Owner's log: the watch connects to KNEIL-7AD1, MTU 247, then `disconnecting: KNEIL service not found`, every few
seconds. NimBLE logs the searched UUID as `a8f50001-3e2c-4c6e-9b1a-6b4e45944c00`; the protocol is
`...-6b4e45494c00`. Cause: `main/kneil_central.c:20`, `KNEIL_UUID128()`, third byte `0x94` must be `0x49`
(little-endian bytes of 6b4e45494c00 are 00 4c 49 45 4e 6b). The scan still matched by the name `KNEIL-`.

Branch: `agent/W3` in `guder_watch_agent`, new from the watch repo's `main` (`git switch -c agent/W3 main`; main is
`864632a`, which contains W1/W2; your worktree must be clean, leave `dependencies.lock` changes uncommitted or restore
it). Report `tasks/W3_report.md` on a new branch `agent/W3` from `main` in `kneil_v4_agent`. Never push, never flash.

## Do
1. Fix the byte.
2. Make this impossible to repeat: the UUID bytes must be checked against the protocol text. Move the 16 bytes into
   `kneil_state.c/.h` (or a small new pure-C file) as `KNEIL_UUID_BASE_LE[16]`, use them in `kneil_central.c`, and add a
   host test that formats the five UUIDs (0x0001, 0x0002, 0x0004, 0x0005, 0x0006) to text and compares with the strings
   `a8f5000X-3e2c-4c6e-9b1a-6b4e45494c00` from `kneil_firmware/protocol/README.md`.
3. Check every other hand-written constant in the new watch files against the KNEIL protocol (CONTROL codes, packet
   types, lengths); list them in the report with PASS/FAIL.

## Checks
Host tests (counts; the new UUID test must FAIL on the old byte and PASS on the fixed one: show both), `idf.py build`
(EIM profile), no new warnings.
