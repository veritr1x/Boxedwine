# First startup optimization

This change removes a single-threaded scheduling starvation case and avoids
launching six `reg.exe` processes before Populous. The performance endpoint is
the first Wine `ddraw_surface1_Flip` log after navigation. It is an initial
presentation request, **not** time to an interactive menu or playable level.

## Changes

`scheduleThread` now appends a waking thread to the runnable queue. Previously,
a client and server could repeatedly wake each other at the front, indefinitely
overtaking an input worker. Populous then spent about 20 seconds waiting on
Wine's `dinput_hook_crit`. The same FIFO approach was already present in the
separate Wine/WebGL experiment; this change ports it to current master.

The regression models repeated client/server wakeups with a continuously ready
input worker. Before the fix that worker received zero of 32 turns. The fixed
scheduler permits bounded progress. This affects cooperative single-threaded
builds; it does not change the pthread scheduler.

`populous-start.c` writes the six existing `regs.cmd` values in one guest
process, then launches and waits for `popTB.exe`. It derives installation paths
from the guest working directory, checks API errors, and leaves game code,
assets and timing settings intact. The helper also accepts `D3DPopTB.exe`, but
this fork's default web build does not currently provide its OpenGL device.

## Reproduce with private inputs

The preparation tool requires an i686 MinGW C compiler in addition to the
[CPU toolchain](Web-CPU-Development.md). It validates the runtime manifest,
copies inputs into a new snapshot directory, builds the launcher, and records
compiler/source/runtime/archive hashes in `workload.json`. It does not update
the SDK or alter source game archives. Its output is excluded from Git.

```sh
python3 tools/web-cpu/cpu.py build --mode profile --target jit
python3 tools/web-cpu/prepare-populous.py \
  --runtime project/emscripten/Build/WebCPU/profile/Jit \
  --wine /path/to/software-wine.zip --app /path/to/private-populous.zip \
  --out tmp/web-cpu/my-populous
python3 tools/web-cpu/cpu.py serve --port 8093
```

The app ZIP must contain `popTB.exe` at its root. Use the URL printed by the
preparation tool under the snapshot's server path. It selects a 640×480, 32-bit
guest desktop, ephemeral storage, and disabled sound. This display configuration
allows the software game to advance into a level; presentation is still imperfect.

Capture without enabling Chrome's CPU sampler. This command deliberately uses
the original unspecified desktop size to reproduce the startup table below;
use the preparation tool's resolution parameters for the level probe:

```sh
node tools/web-cpu/profile-browser.mjs --headless --no-profile \
  --seconds 70 --stop-on 'ddraw_surface1_Flip' \
  --url 'http://127.0.0.1:8093/tmp/web-cpu/my-populous/boxedwine.html?root=wine.zip&app=app.zip&overlay=launch.zip&p=Z%3A%5Ctmp%5Cpopulous-start.exe&storage=memory&sound=false' \
  --manifest tmp/web-cpu/my-populous/manifest.json \
  --out tmp/web-cpu/my-startup-run
```

`capture.json` contains the elapsed milliseconds from navigation to the first
matching console line; `console.json` includes each event's elapsed time. A
missing milestone fails the capture. Each invocation uses a fresh owned Chrome
profile. Local file serving does not model a cold internet download.

Keep baseline and candidate runtimes in separate snapshots. Alternate runs
with identical Wine/app/overlay hashes and startup settings. For the original
fixture's six-process launch, select `p=baseline.bat`. For the consolidated
launch, select `p=Z%3A%5Ctmp%5Cpopulous-start.exe`. Do not run compilers, CPU
samplers, or another game benchmark during the timing runs.

## Validation and remaining game work

On 2026-09-13, three alternating runs per arm on an Apple M5 Max / 48 GiB,
Chrome 152.0.7977.83, Emscripten 6.0.9 produced:

| Configuration | Runs (seconds) | Median | Input lock timeouts |
| --- | --- | --- | --- |
| Original scheduler, six registry processes | 40.559, 41.536, 45.564 | 41.536 s | 3 / 3 |
| Fair scheduler, six registry processes | 22.458, 22.320, 22.580 | 22.458 s | 0 / 3 |
| Fair scheduler, consolidated setup | 17.019, 16.916, 17.182 | 17.019 s | 0 / 3 |

The median reduction is **59.0%** for this startup endpoint. Fair scheduling
alone reduces it by 45.9%; consolidating setup removes a further 5.439 seconds.
These are `-O2` profile-mode runtimes with function names but **no active CPU
sampler**, fresh browser profiles, identical ZIP inputs, memory storage, and
sound disabled. No other game runs or compilers ran during this comparison.
The local filesystem was warm; three runs do not establish browser/hardware
generality. Full hashes and raw run values are in the
[measurement record](benchmarks/2026-09-13-startup.json); raw captures are under
`tmp/web-cpu/startup-matched/`.

The starvation regression fails before the fix. With the fix, all 768 ST JIT
fast tests and all 748 ST interpreter fast tests pass. MinGW builds the helper
with `-Wall -Wextra -Werror`; the preparation tool successfully stages and boots
both JIT and interpreter snapshots. MSVC project entries include the regression;
MSVC itself was not run on this macOS host. Prior MT JIT concurrency failures
remain separate and unresolved.

With the original default desktop size, the software game displays a corrupted
image after its intro; this reproduces with the interpreter and with the
separate software Wine package. A subsequent `resolution=640x480&bpp=32` probe
advances through the menus into a rendered level with normal colors using
canvas click/Enter input. A dialog still renders incorrectly, and sustained
gameplay, input correctness and audio are not established. Selecting an 8-bit
desktop instead produces incorrect palette colors. The earlier WebGL-patched
Wine package fails to create the Direct3D game device in this build.

A 12-second CPU profile after 45 seconds of software startup attributes 15.5%
of sampled wall time to `wasmStartJITOp`, 12.5% to `normal_movsb_op`, and 8.1% to
`wasmHelper_fetchNextOp`; 27.3% is idle. Game addresses `0x004ba8a7/0x004ba8a9`
poll a timer, so faster emulation may simply increase waiting there. The next
game phase needs a working presentation/input path and a fixed loaded save
before optimizing copying/dispatch or claiming an FPS improvement. Quake II
timedemo remains the planned open engine workload and has not been measured.

The later 640×480 level probe dismissed the dialog with mouse/Space input and
captured a visibly changing world. Its separate 15-second CPU profile attributes
19.9% to `wasmStartJITOp`, 7.4% to `wasmHelper_fetchNextOp`, and 7.1% to
`normal_movsb_op` (23.8% idle). This identifies dispatch and repeated byte copies
as the next CPU targets; it is not a measured gameplay speedup. The original
game's timer-polling loop is still prominent. Normal simulation pacing, a fixed
saved workload, and distinct game-frame telemetry must gate that comparison.

Local diagnostic evidence: `tmp/web-cpu/software-intro-stall-profile/`,
`gameplay-software-root-probe/`, `gameplay-interpreter-probe/`, and
`gameplay-640-probe/`, and `gameplay-level-profile/`. Profiles and
screenshots establish these diagnostic observations, not playable-game parity.
