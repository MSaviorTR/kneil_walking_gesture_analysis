# Task T1_fix (worker deepseek): fixes to the watch therapy mode after the manager's review

Same worktree and branch as T1: continue on `agent/T1` in `guder_watch_agent` (new commits, no rebase). Report
`tasks/T1_fix_report.md` on `agent/T1` in `kneil_v4_agent`, committed last. Never push, never flash.

## Findings (checked in the code by the manager)
1. **`idx_raw` is not reset on connect and disconnect** (`kneil_central.c`, the two lines
   `idx_live = idx_info = idx_summary = -1;` in `gap_event`). Only `kneil_central_on_reset()` resets it. After a device
   with RAW, a device without RAW would subscribe a stale slot. Add `idx_raw` to both lines.
2. **RAW left on at reconnect.** The implant keeps `raw_on` over a link loss (`kneil_firmware/src/kneil_live.c`
   line 214) and sends RAW whenever connected + subscribed; the watch now subscribes RAW on every connection. So a RAW
   stream left on by a lost session or by the PC app restarts at every reconnect and costs implant battery. Fix: on
   **every** new KNEIL connection (after the subscriptions), if no therapy session or calibration is running, queue
   CONTROL `0x11` once. Host-test it as a pure function if possible (connected + idle -> stop).
3. **The straight check must not rescale the angle.** After knee surgery most patients cannot reach 0 deg (extension
   lag of 10-20 deg is common), and that deficit is exactly what the physiotherapist wants to see. Today
   `scale = 90 / travel` hides it (a patient who reaches 20 deg is shown 0 deg). An accelerometer tilt has no scale
   error. Keep `scale = 1` always; the straight check only (a) checks the sign (straightening must lower phi, else
   say "sensor orientation not as expected" and refuse the session) and (b) logs and shows the best extension reached
   (e.g. "Straight check: 18 deg"). Update the tests (a patient reaching 20 deg must read about 20 deg).
4. **Wording**: `connection_lost` says "Stop and check the implant": frightening for a patient. Use "Connection lost.
   Rest for a moment; the watch will reconnect." Regenerate the clips (`tools/make_voice_clips.py`) and report the new
   size.
5. **Visible warnings** (report section 5, items 6 and 10): show a short line on the therapy page when the speaker is
   unavailable ("Speaker off: vibration cues") and when the log storage is not mounted ("Log not saved").
6. `slow` clip: the warning fires when the movement is **too fast** (> 30 deg/s); make the text say so: "Too fast.
   Move slowly and smoothly." (same regeneration).

## Checks
Host tests (counts; new tests for 1-3), `idf.py build` with no new warnings, image size, the three simulator renders
(and one showing the speaker-off / log-not-saved lines). List each changed line range per finding.
