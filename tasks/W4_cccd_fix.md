# Task W4: the watch subscribes to the wrong CCCD (found on hardware, 17 Nov 2026)

After W3 the link is stable, but the owner's log shows all three subscriptions writing the same descriptor:
`discover all descriptors; chr_val_handle=21 end_handle=33` -> `write; att_handle=33`, then the same for
chr_val_handle=29 and 32: **all three write handle 33** (the SUMMARY CCCD). Cause: `main/kneil_central.c`
`subscribe_next()` searches descriptors from the value handle to `svc_end`, and `on_sub_dsc()` keeps the **last** CCCD
it sees. So LIVE and INFO are never enabled and the KNEIL page gets no LIVE packets.

Branch `agent/W4` from the watch repo's `main` (`16d6579`) in `guder_watch_agent`; report `tasks/W4_report.md` on
`agent/W4` from `main` in `kneil_v4_agent`. Never push, never flash. Leave `dependencies.lock` uncommitted.

## Do
1. In `on_chrs()` keep the definition handle of every characteristic in the service. A characteristic's descriptors
   lie between its value handle + 1 and the next characteristic's definition handle - 1 (or `svc_end` for the last).
   Search only that range, and take the **first** CCCD (0x2902) in it.
2. Put the range/choice logic in a pure-C function (in `kneil_state.c` or a new file) and host-test it with the real
   layout from the log: service 19..33, LIVE value 21, INFO value 29, SUMMARY value 32, the last CCCD 33; also RAW and
   CONTROL in between (RAW has a CCCD, CONTROL has none). Expected: three different CCCD handles (LIVE 22, INFO 30,
   SUMMARY 33 if each CCCD follows its value). The test must fail on the old "last CCCD up to svc_end" rule.
3. Log one line per subscription: `subscribed <name>: value <h> cccd <h>`, and one INFO line on the first LIVE packet
   after a connect (`first LIVE packet, v<version>, class <name>`), so the owner's next log proves it.
4. Notify routing (`handle_notify`) must match on the value handles; check it.

## Checks
Host tests (counts; new test fails on the old rule, show it), `idf.py build` (EIM profile), no new warnings.
