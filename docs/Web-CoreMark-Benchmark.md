# Open x86 CPU benchmark: CoreMark

Use the unmodified [EEMBC CoreMark algorithms](https://github.com/eembc/coremark)
through Wine and Boxedwine to measure a fixed amount of x86 CPU work. This
complements the private Populous and Majesty workloads; it does not measure
rendering, game FPS, audio, or the planned Quake II timedemo.

## Prepare

Install the Emscripten tooling described in [Web CPU development](Web-CPU-Development.md),
Node with built-in WebSocket support, Chrome, and an `i686-w64-mingw32-gcc`
cross-compiler. The capture uses the existing dependency-free CDP tool and owns
its Chrome process/profile. No Playwright or game assets are needed. A local
Wine filesystem ZIP is still required.

```sh
git clone https://github.com/eembc/coremark.git tmp/web-cpu/coremark-source
git -C tmp/web-cpu/coremark-source checkout 1f483d5b8316753a742cbf5590caf5bd0a4e4777
python3 tools/web-cpu/cpu.py build --mode release --target jit
python3 tools/web-cpu/prepare-coremark.py \
  --source tmp/web-cpu/coremark-source \
  --runtime project/emscripten/Build/WebCPU/release/Jit \
  --wine /path/to/wine.zip \
  --out tmp/web-cpu/coremark-control
python3 tools/web-cpu/cpu.py serve --port 8093
```

Run the server in a separate terminal. Pass `--cc /path/to/i686-w64-mingw32-gcc`
if the cross-compiler is outside PATH. The preparation tool checks every
algorithm/header against the pinned upstream revision and records source, port,
compiler, executable, ZIP and runtime hashes. It never changes the source
checkout or supplied Wine archive and requires a new output directory.

The port uses Windows `QueryPerformanceCounter` for elapsed wall time,
millisecond result ticks, command-line seeds, one context and a 2000-byte total
dataset. `-mwindows` retains inherited output handles without Wine launching a
separate console renderer; this avoids terminal redraw/line-wrapping artifacts
in captured benchmark results. The port prints and flushes timing markers
outside the measured interval so the host can check the guest clock. All
algorithm translation units use the same compiler flags, without LTO or PGO.
The supplied port header is adapted from EEMBC's Apache-2.0 simple port; its
notice and license are retained in `tools/web-cpu/coremark-port/`.

## Measure

Calibrate a fixed iteration count in an excluded pilot before timing an
optimization. For example, on the recorded M5 Max setup 30,000 performance-seed
iterations take about 14 seconds. Slower or faster machines need their own
calibration. [CoreMark's run rules](https://github.com/eembc/coremark#run-rules)
require at least ten seconds and successful validation for both seed sets.

```sh
python3 tools/web-cpu/measure-coremark.py \
  --runtime tmp/web-cpu/coremark-control \
  --out tmp/web-cpu/coremark-performance-1 --iterations 30000
python3 tools/web-cpu/measure-coremark.py \
  --runtime tmp/web-cpu/coremark-control \
  --out tmp/web-cpu/coremark-validation-1 --iterations 30000 --seed validation
```

The timing command requires a release runtime without function-name profiling,
debug instrumentation, or JIT counters. It checks runtime/workload hashes,
requires the exact iteration count and expected seed/list/matrix/state CRCs,
rejects runs below ten seconds, and compares the guest elapsed time against
host-received timing markers (within 1% or 250 ms, whichever is larger).
`result.json` records the timed-loop seconds and iterations/second;
`capture.json`, `console.json`, `screen.png`, and `chrome.log` preserve capture
provenance and errors. A passing benchmark requires both the guest validation
and a successful browser capture.

For A/B measurements, freeze both runtime snapshots and one guest binary, Wine
ZIP, iteration count and seed set. Use fresh output directories and alternating
runs with the same browser/host, no active CPU sampler or compiler, and no other
owned benchmark running. Compare elapsed time for the fixed work; keep startup
and private-game compatibility evidence separate. Do not mix counter builds,
interrupted runs, failed validation, or calibration pilots into accepted results.
