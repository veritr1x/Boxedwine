# Wasm JIT dispatch experiments

Both isolated dispatch candidates were reverted: their five-pair median CPU
time reductions were **0.6% and 0.7%**. This pass retains measurement tooling
and a repeatable game starting point, with no new runtime performance claim.

## Workload and diagnosis

This pass moves from the [completed Majesty HD startup work](Web-Majesty-XAttr-Optimization.md)
to steady execution. It adds an isolated counter build and a reproducible
[open x86 CoreMark workload](Web-CoreMark-Benchmark.md).

A private Majesty Gold HD 1.5.2.28 session entered **Quest for the Holy Chalice
(Advanced)**. A clean 15-second CPU profile of the running mission attributed
19.56% of sampled time to `wasmStartJITOp` and 4.49% to
`wasmHelper_fetchNextOp`, with 26.19% idle. These are diagnostic self-time
shares, including counter overhead, and cannot establish gameplay speed.

Across a separate clean 35-second counter interval in the same mission,
approximately 99.994% of observed chain targets were eligible for compiled
chaining. Estimated mean chain length was 1,335 blocks, with the existing
single-threaded cap of 2,048. Memory-page-array checks recorded no refreshes
in that interval. The counters use sampled estimates; their nested timing
fields are not additive. Chaining is already effective in this workload.
Reducing work at each transition remains a candidate for investigation.

## Isolated candidates

1. **Recording helper.** Marking the disabled transition-recording helper
   `noinline` moved a 624-byte Wasm stack reservation behind its enabled branch.
   Binaryen subsequently re-inlined the helper, so this did not remove all cold
   code or locals from the final function. Five matched pairs saved only 0.6%
   at the median. This candidate was reverted.
2. **First-block logging.** Moving the first-block varargs log into a `noinline`
   helper removed the dispatch function's 16-byte stack frame and unconditional
   spill of the table index before every compiled-block call. The first-call
   condition and message were preserved. Named final Wasm confirms the helper
   remains separate and the dispatch stack operations disappear. Five matched
   pairs saved only 0.7% at the median, with one pair slower and candidate run
   variation larger than the median shift. This candidate was also reverted.

These experiments do not alter guest instruction generation, cache policy,
chain bounds, scheduling, graphics or private game data.

## Measurement method

Apple M5 Max / 48 GiB, Chrome 152.0.7977.83, Emscripten 6.0.9, Node 26.5.0,
single-threaded release JIT at `-O2`, no profiling names or counters. Each
experiment uses five alternating baseline/candidate pairs with a fresh owned
headless Chrome process. There are no active compiler jobs, CPU samplers or
other owned benchmarks during accepted timing.

The fixed work is 30,000 performance-seed iterations of the unmodified EEMBC
CoreMark algorithms at revision `1f483d5b8316753a742cbf5590caf5bd0a4e4777`.
Both arms use the same x86 executable, Wine archive and command-line seeds.
The Windows port uses `QueryPerformanceCounter`; host-received markers outside
the timed interval cross-check the guest clock. All accepted performance
runs exceed ten seconds and pass the expected seed/list/matrix/state CRCs.

Only the timed loop is compared. Browser/Wine startup, guest setup, validation
output and capture cleanup are outside this interval. Calibration pilots,
failed console-subsystem captures and the diagnostic mission profile are
excluded. The first experiment did not run the separate validation seed and
is reported only as an experimental comparison, not a fully validated
CoreMark score. None of these CPU results represents game FPS.

## Results and reproducibility

| Candidate | Baseline seconds | Candidate seconds | Median reduction | Decision |
| --- | --- | --- | ---: | --- |
| Recording helper | 14.207, 14.525, 14.308, 14.382, 14.284 | 14.118, 14.112, 14.224, 14.231, 14.242 | 0.59% | Reverted |
| First-block logging | 14.245, 14.281, 14.233, 14.259, 14.185 | 14.323, 14.207, 14.059, 13.927, 14.143 | 0.72% | Reverted |

The corresponding medians are 14.308 → 14.224 seconds and 14.245 → 14.143
seconds. All 20 performance captures passed their CRC, duration and clock
checks. Both candidates separately passed all 772 single-threaded JIT fast
tests. No new MT or interpreter compatibility claim is made for these rejected
patches. This is a small, single-host series, not evidence of statistical
significance. CoreMark's instruction mix can respond differently from a game.

The [public measurement record](benchmarks/2026-09-13-jit-dispatch.json) includes
both exact experimental patches against `b9899ed4`, build manifests, compiler
flags, runtime/guest hashes, per-run results, artifact hashes, and the clean
mission diagnostic. The baseline contains the completed timestamp and xattr
startup improvements. Private raw outputs remain under
`tmp/web-cpu/dispatch-coremark-matched/` and
`tmp/web-cpu/dispatch-log-matched/`; private assets and screenshots are excluded
from the public record. Follow the [CoreMark instructions](Web-CoreMark-Benchmark.md)
to prepare and measure a fresh snapshot.

The baseline and logging candidate also passed the separate validation seeds
at 30,000 iterations (14.342 and 14.099 seconds), including expected CRCs and
timer checks. These one-off validation runs are outside the performance table.
The runner additionally records a failed result when Chrome cannot launch,
and rejects a runtime manifest that differs from the prepared workload.

## Fixed Majesty HD starting point

The campaign save **(Quest for the Holy Chalice) 2 Days.GMP** was exported from
one session, placed in a private copy of the Wine filesystem, and successfully
loaded in a fresh owned Chrome session. The load menu recognizes the save;
mission screenshots then show **day 3 / treasury 6,844 → day 4 / treasury 7,885**.
No page exceptions occurred. Existing Wine audio-decoder errors remain, with
emulator sound disabled and the same DX9 fallback / `-dib` graphics path.
This establishes a reusable starting save and short running-mission smoke,
not a deterministic timedemo, FPS result, audio validation or IDBFS persistence.

A 15-second profile after loading, using the normal profile build without JIT
counters, attributes 20.11% of sampled time to `wasmStartJITOp` and 5.46% to
`wasmHelper_fetchNextOp` (26.12% idle). No compiler or other owned benchmark ran
in this window. This supports continuing dispatch investigation, but the two
CoreMark experiments above do not establish a meaningful game improvement.

Private reproduction uses `tmp/web-cpu/interactive-majesty-fixed.mjs` with
`tmp/web-cpu/majesty-fixed-profile`, the existing screenshot matcher, and a new
output directory. It selects the main `MajestyHD.exe`, not the old executable.
After the menu is recognized, select Load Game at canvas coordinate `(204,577)`
and load the selected save at `(265,648)` in the 1024×768 game coordinate space.
The retained `actions.json` records the actual sequence and observation times.

The overlay contains only the exported save, `MajXPrefs` and
`questdata_majx.sav` under Wine's `users/username/Documents/My Games/MajestyHD/`.
The public record hashes the overlay separately from the original Wine ZIP and
records all three exports. Original installation files and Wine assets remain
unchanged; no private game binary, save, archive or screenshot is published.
The release runtime was rebuilt after reverting both experiments and is
byte-identical to the baseline Wasm (`73efe9d9…`).

The next experiment should measure repeated execution from this fixed save and
inspect which hot transitions still return through the dispatcher. Existing
module grouping, direct-loop and offline tail-call support must be accounted
for before adding another dispatch path.
