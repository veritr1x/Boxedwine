# Web CPU development

The first target is the CPU. This fork starts from upstream master
`296ff0fa14e0dd1debb0f5898e2e33504f2ad066` (2026-09-06). Upstream's README TODO
about needing a Wasm JIT is stale: the JIT is already implemented. The work is
to make its browser execution faster and dependable for games.

Populous: The Beginning is the first compatibility target. Quake II timedemo
is the planned repeatable game workload. Its engine source is open; game/demo
data must be supplied separately under its applicable license. The first
[Populous startup comparison](Web-Startup-Optimization.md) is available;
playable-game throughput and Quake II have not been benchmarked in this fork.
Test-suite timings are not game results.

## Toolchain and isolated builds

Requirements: Python 3.9+, Node with built-in WebSocket support (tested with
26.5.0), an installed Emscripten SDK, and Chrome. No npm dependencies or global
browser-profile changes are needed. Validated locally with Emscripten 6.0.9.

```sh
python3 tools/web-cpu/cpu.py configure --emsdk /path/to/emsdk
python3 tools/web-cpu/cpu.py doctor
python3 tools/web-cpu/cpu.py build --mode profile
python3 tools/web-cpu/cpu.py build --mode debug
python3 tools/web-cpu/cpu.py build --mode release
python3 tools/web-cpu/cpu.py build --mode profile --target testMultiThreadedJit
```

`configure` records only a local SDK path in ignored `tmp/web-cpu/config.json`.
It reuses the SDK without updating it. `doctor` locates the compiler, Wasm
disassembler, LLVM object/DWARF inspectors, symbolizer, Node, and Chrome.

| Mode | Purpose | Flags |
| --- | --- | --- |
| release | Uninstrumented control | Upstream `-O2`, JIT SIMD/tail-call flags |
| profile | Find emulator and generated guest hotspots | `-O2`, function and generated-block names |
| debug | Source locations, variables, failure investigation | `-O1`, DWARF, source map, symbol map, assertions, stack checks |

Outputs live in `project/emscripten/Build/WebCPU/<mode>/<Target>/`. Each build
has `build.log`, `configuration.json`, and a `manifest.json` recording source
state, exact command, compiler version, and binary SHA-256 hashes. A source
change during the build prevents manifest publication. A configuration change
requires `--fresh`, which removes only the selected tool-owned build directory.
Normal source edits use Make's dependency tracking. Upstream Make targets and
their default `Build/` output paths remain available.

For actual game runtimes use `--target jit` or `--target multiThreadedJit`.
`--target test` and `--target testMultiThreaded` build the ST/MT interpreter
CPU test controls. Test binaries need no
Wine filesystem or private game data.

The build also resolves three incompatibilities with Emscripten 6.0.9: C++
linking uses `em++`, the module broker supports the current pthread inventory,
and pthread command IDs come from the SDK preprocessor. Legacy string commands
remain supported. The production broker and its C++/JS test helpers use the
same command mapping.

## Fast CPU validation and Node profiles

```sh
python3 tools/web-cpu/cpu.py run --mode profile
python3 tools/web-cpu/cpu.py run --mode debug --filter 'WASM JIT'
python3 tools/web-cpu/cpu.py run --mode profile --list --filter 'memory'
python3 tools/web-cpu/cpu.py run --mode profile --filter 'WASM JIT' --profile
node tools/web-cpu/summarize-profile.mjs tmp/web-cpu/runs/<run>/cpu.cpuprofile
node project/emscripten/testJitWorkerInventory.mjs
```

Runs default to upstream's **fast mode**, which reduces operand combinations;
use `--full` for the exhaustive operand matrix. Filters are case-sensitive
substrings. Empty/missing filter values and zero matches fail with exit code 2.
Existing numeric range arguments still work when invoking the binary directly.
Every wrapper run stores its command, exit code, build manifest, and console
log in a new ignored `tmp/web-cpu/runs/` directory. `--profile` also writes a
Chrome-compatible `.cpuprofile` for ST tests. Use the browser profiler for MT
worker sampling. A run times out after 300 seconds (exit 124); set `--timeout`
higher for exhaustive runs. The summary reports sampled **self time**.
Do not compare profiled test durations as a performance result.

## Browser CPU and pthread profiles

Start the loopback server; it supplies COOP/COEP headers for shared Wasm memory:

```sh
python3 tools/web-cpu/cpu.py serve --port 8093
```

Open the test harness at:

```text
http://127.0.0.1:8093/tools/web-cpu/harness.html?build=debug/TestJit&arg=-fast&arg=--filter&arg=WASM%20JIT
```

The harness restores its parsed arguments in `preInit` because upstream's
`--emrun` glue otherwise replaces `Module.arguments` with the raw URL query.
The console's `Running ... in fast mode` line and test names confirm selection.

For a bounded automated profile of the page **and all dedicated workers**:

```sh
node tools/web-cpu/profile-browser.mjs \
  --url 'http://127.0.0.1:8093/tools/web-cpu/harness.html?build=profile/TestMultiThreadedJit&arg=-fast&arg=--filter&arg=module%20broker' \
  --tests --headless --seconds 60 \
  --manifest project/emscripten/Build/WebCPU/profile/TestMultiThreadedJit/manifest.json \
  --out tmp/web-cpu/my-mt-profile
node tools/web-cpu/summarize-profile.mjs tmp/web-cpu/my-mt-profile/*.cpuprofile
```

The example selects the four broker transport/cache/lifecycle tests. Run the
full JIT diagnostic group through the Node wrapper as well: some diagnostics
intentionally drop thread starts and wait for timeouts, so they are unsuitable
for a short interactive profile.

The profiler launches its own Chrome profile, recursively attaches through CDP,
and records one `.cpuprofile` per page/worker plus console logs, a screenshot,
Chrome version, timestamps, and the supplied build manifest. It excludes
extension/service-worker targets and refuses to overwrite a capture directory.
Missing test completion, runtime exceptions, lost active targets, or absent
samples fail the run. Warmup defaults to zero; for a game use `--warmup 30
--seconds 15` and omit `--tests`. A zero-warmup profile includes loading and JIT
compilation, useful for startup diagnosis but different from steady gameplay.
`--chrome /path/to/chrome` or `CHROME_PATH` selects another executable.

Capture the game's active pthread, not just its page. Idle worker samples must
not be counted as useful guest work. CPU sampling perturbs execution: separate
profiling windows from alternating, unprofiled performance runs. Headless runs
validate tooling, not input, audio, displayed frame rate, or game playability.
The supplied manifest identifies local build inputs; for an external game URL,
also verify that its served runtime and asset hashes match that manifest.

## Source and instruction debugging

In Chrome DevTools, open the debug harness and inspect Sources. The debug Wasm
has a source map resolving back to this checkout and embedded DWARF. Source
locations need no extension; full C++ variable inspection uses Chrome's
optional **C/C++ DevTools Support (DWARF)** extension. That extension is not
installed or changed by these tools.

Useful first breakpoints:

| Source | Investigate |
| --- | --- |
| `source/emulation/cpu/wasm/jitWasmCodeGen.cpp` | `wasmStartJITOp`, `wasmHelper_fetchNextOp`, inline-memory helpers, compilation/installation |
| `source/emulation/cpu/normal/normalCPU.cpp` | Interpreter fallback and dispatch |
| `source/emulation/softmmu/soft_code_page.cpp` | Code writes and invalidation |
| `source/kernel/kscheduler.cpp` | Guest scheduling, yields, exception boundaries |
| `project/emscripten/boxedwine-wasm-jit-module-broker.js` | Pthread installation, ownership, module delivery |

```sh
python3 tools/web-cpu/cpu.py tool wasm-dis \
  project/emscripten/Build/WebCPU/profile/TestJit/boxedwine.wasm -o tmp/web-cpu/runtime.wat
python3 tools/web-cpu/cpu.py tool llvm-dwarfdump --debug-info \
  project/emscripten/Build/WebCPU/debug/TestJit/boxedwine.wasm
python3 tools/web-cpu/cpu.py tool emsymbolizer --help
python3 tools/web-cpu/cpu.py tool llvm-objdump --file-headers --section-headers /path/to/game.exe
```

DWARF describes the C++ emulator, not the original proprietary game source.
Generated JIT block names identify guest process/file/offset/EIP when available;
anonymous test code may be labeled `Unknown`. PE virtual addresses, PE RVAs,
file offsets, and Wasm offsets are different address spaces.

## CPU implementation sequence

1. Keep the interpreter, ST JIT, and MT JIT controls buildable. Validate flags,
   x87/SSE, unaligned/cross-page memory faults, self-modifying code, signals,
   code retirement, and worker-local module visibility before changing codegen.
2. Establish matching Populous and Quake II workloads with fixed binary/save/demo,
   Wine filesystem, graphics path, pacing, resolution, and runtime/cache hashes.
   Profile startup separately from sustained simulation/rendering. Begin at
   modest resolution to help distinguish CPU cost from GPU/presentation cost.
3. Rank actual CPU self time: generated guest code; interpreted fallback;
   JIT emission/compilation/installation; memory helpers; dispatch; Wine/kernel
   waits and IPC. Read existing `BOXEDWINE_WASM_JIT_PROFILE`, helper/fallback
   statistics documentation before enabling counters. Counter builds are
   separate configurations and are not timing controls.
4. Change one measured cost at a time: specialize hot helper/fallback operations,
   improve hot-region register/flag retention, reduce repeated module work,
   or refine memory/dispatch paths. Upstream already implements register locals,
   inline TLBs, SIMD, grouped modules, and direct Wasm `call_indirect` dispatch;
   simply enabling those is not a new optimization.
5. Keep a candidate only after correctness checks and alternating unprofiled
   game runs show improvement, including p95 frame times and input/audio behavior.
   No blanket speedup or near-native performance claim is justified yet.

## Reuse the existing graphics work later

`../wine-web` contains patched Wine/Boxedwine WebGL work and private Populous
runtime inputs. `../d3d-webgpu` contains the Direct3D2 capture/replay/live WebGPU
bridge, workload fixtures, image comparison, and prior JIT experiments. Its
`scripts/jit-game-benchmark.mjs`, `scripts/game-workload.mjs`,
`scripts/dump-hot-wasm.mjs`, and `docs/jit-optimization-log.md` are integration
references. Those checkouts and their paused work have not been changed.

Do not blindly copy their old compiled modules or JIT caches into this runtime:
the CPU layout, exported bridge ABI, graphics patches and cache provenance must
match. First port or isolate the required graphics bridge changes in this fork,
then regenerate matching caches and validate reference images. Full Wine service
replacement or a new graphics backend is outside this CPU tooling change.

The eventual architecture is x86 game/Wine code translated to CPU Wasm, with
graphics translation producing WebGPU commands and WGSL shaders for the GPU.
Wasm itself does not execute as GPU shader code. Emscripten's Emdawnwebgpu port
offers a C API binding to browser WebGPU; it is not a complete Direct3D backend.

## Validation recorded on 2026-09-13

Local tools: Emscripten 6.0.9, Node 26.5.0, Chrome 152.0.7977.83 on macOS.
These are correctness/tooling results, not comparative CPU performance.

| Check | Result | Local artifact under `tmp/web-cpu/` |
| --- | --- | --- |
| ST JIT release, all fast tests | 767 passed | `runs/20260913T022825.439208Z` |
| ST JIT profile, all fast tests plus Node sampling | 767 passed, named CPU profile saved | `runs/20260913T021258.681686Z` |
| ST interpreter release, all fast tests | 747 passed | `runs/20260913T023241.044823Z` |
| MT interpreter release, all fast tests | 768 passed | `runs/20260913T023413.182225Z` |
| ST JIT debug, `WASM JIT` filter | 13 passed; DWARF and 727-source map present | `runs/20260913T021657.837327Z` |
| MT JIT profile, `WASM JIT` filter | 23 passed | `runs/20260913T022923.875391Z` |
| Chrome MT JIT, `module broker` filter | 4 passed; page plus 8 worker profiles, no capture failures | `browser-mt-broker-verified` |
| Chrome debug ST JIT, SSE compare filter | Passed; CPU profile saved | `browser-debug-verified` |
| Legacy/current worker inventory and command transport | Both VM fixtures passed | `node project/emscripten/testJitWorkerInventory.mjs` |
| Full MT JIT profile suite | **796 passed, 2 failed** | `runs/20260913T023019.807554Z` |

The ST game runtime also builds with `build --mode profile --target jit`.
Actual game launch and benchmarks remain pending.

**Open MT correctness issue:** the full 798-test fast suite reported invalid
locked/plain-store ordering for implicit `xchg` (phase 946) and locked `xadd`
(phase 815). An earlier full run also reported a failed `cmpxchg` ordering case
(phase 875). Five subsequent runs of the seven `against plain store` tests
passed, as did the interpreter control. This does not clear the full-suite
failures. The root cause and any relationship to audio stutter are unproven;
retain the failed logs and investigate suite state, codegen and memory ordering
before accepting MT performance changes. No locked-instruction implementation
was changed in this tooling work.

The full 23-test browser JIT diagnostic run completed with zero test failures,
but `Profiler.stop` timed out after its deliberate thread-start failure tests
(`browser-mt-protocol-complete`). That is a **failed profile capture**. Use the
bounded broker filter above for worker-profiling validation and the Node wrapper
for the full diagnostic group. Idle/futex-wait samples in broker profiles are
not useful game work.

Raw logs, browser profiles, build manifests, and failed attempts remain local
in ignored `tmp/web-cpu/` and `project/emscripten/Build/WebCPU/`. Reproduce the
commands above on a new machine; no private game assets are included.

## Primary references

- [Emscripten debugging and symbolization](https://emscripten.org/docs/porting/Debugging.html)
- [Chrome C/C++ Wasm debugging](https://developer.chrome.com/docs/devtools/wasm)
- [Emscripten pthreads and cross-origin isolation](https://emscripten.org/docs/porting/pthreads.html)
- [Emscripten WebGPU bindings](https://emscripten.org/docs/porting/multimedia_and_graphics/WebGPU-support.html)
- [WGSL specification](https://gpuweb.github.io/gpuweb/wgsl/)
- [Quake II engine source](https://github.com/id-Software/Quake-2)
