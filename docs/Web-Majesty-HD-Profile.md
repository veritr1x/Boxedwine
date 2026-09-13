# Majesty Gold HD CPU diagnosis

Follow-up: [timestamp lookup consolidation](Web-Majesty-Startup-Optimization.md)
now has a matched three-pair startup measurement: median 150.155 → 86.272 seconds.
The diagnostic session below predates that change.

The main **`MajestyHD.exe`, version 1.5.2.28**, reaches an animated menu and a
running Random (Beginner) mission in this fork. Its CPU profile shares Populous's
JIT dispatch hotspot, but not its repeated byte-copy hotspot. Majesty's lengthy
asset initialization is dominated by filesystem metadata work.

The old executable is excluded from the private workload archive. The tested
main executable's SHA-256 is
`65c6dd32c3d873c2e320bdaa2de1b00488af85b44573fd0fd82f79a2ffd37792`.
Screenshots show day 0 / treasury 20030 progressing to day 1 / treasury 20173.
This establishes a rendering and simulation smoke test, not sustained playability.

## Configuration and evidence

The run uses the same single-threaded `-O2` profile runtime and software Wine ZIP
as the [Populous level profile](Web-Startup-Optimization.md): source commit
`f57fc0a7a130c2d9d9ae0ed9eec438dfd3560adf`, Wasm SHA-256
`3f62d99b236028f400e7b6badb6e63527e3c25c1ed0bcf1bef4d1e0534a1f837`,
Wine SHA-256 `aad6bb6725b00500c9af935ec001bc33f7d6351d52e3d38b1a2078a0a2301718`.
Host: Apple M5 Max, 48 GiB; Chrome 152.0.7977.83, headless, fresh owned browser.

Majesty uses 1024×768, 32-bit color, memory storage, disabled emulator sound, and
`-nointro -nosuspend -dib`. The game first reports failed DX9 initialization and
offers its fallback renderer; that dialog was accepted. This is still the main
HD executable. **D3D9 and WebGPU performance are not measured by this run.** Wine
also reports audio decoder/filter errors; audio and save persistence are untested.

All game ZIP entries use `ZIP_STORED`. The previous separate Majesty trial found
compressed entries expensive during seeking. In current source,
`FsZip::setupZipRead` restarts decompression after an entry switch or backward
seek, while `FsZipOpenNode::readNative` already has a direct-read path for stored
entries. This run does not repeat the compressed-versus-stored comparison.

The [machine-readable record](benchmarks/2026-09-13-majesty-hd.json) contains input
and profile hashes, browser version, raw self-time percentages, capture windows,
and actions. Local screenshots, console logs, and Chrome-importable profiles are
in `tmp/web-cpu/majesty-hd-probe/`. Inputs remain in ignored private snapshots.

## What the profiles show

Percentages below are sampled **self time, including idle**. Dispatch combines
`wasmStartJITOp` and `wasmHelper_fetchNextOp`. Two approximately 15-second windows
were captured in the same Majesty mission with a fixed camera. Populous is the
previously captured 15-second level window at 640×480. These compare hotspot
patterns across games, not throughput or optimization gains.

| Sampled cost | Populous level | Majesty mission A | Majesty mission B |
| --- | ---: | ---: | ---: |
| JIT entry + next-block dispatch | 27.29% | 20.83% | 20.96% |
| `normal_movsb_op` | 7.08% | 0.13% | 0.18% |
| `lookupPath` + `normalize` | 0.008% | 0.007% | 0.008% |
| `unzReadCurrentFile` | 1.73% | 0% sampled | 0% sampled |
| Idle | 23.77% | 26.18% | 26.13% |

Majesty's two earlier black-screen initialization windows have a different
shape: `lookupPath` + `normalize` account for **39.86% and 40.47%**, while combined
dispatch accounts for 9.25% and 8.85%. No `unzReadCurrentFile` samples occur in
those windows with stored game entries. The first 15 seconds, which include
Wine loading and waiting on the DX9 dialog, do contain 19.30% in that ZIP reader;
that mixed phase must not be mistaken for the later asset-indexing profile.

The heavy lookup stacks pass through `___syscall_stat64` to
`FsFileNode::lastModified`, `lastModifiedNano`, `lastAccessed`, and
`lastAccessedNano`, under guest `fstat64`. Another frequent stack passes through
`___syscall_faccessat` and `getXAttrResult`. Source inspection explains the repeated
work: `KFile::stat` requests each timestamp separately; the file-node accessors
each issue a host stat, and nanosecond/ctime fallbacks can call the accessors
again. Under Emscripten these operations traverse the JavaScript filesystem.
This identifies a concrete optimization seam; it does not yet quantify the gain
from changing it.

For startup, the next Majesty candidate is one coherent metadata snapshot per
guest stat operation, preserving ZIP fallback, timestamp overrides, hard links,
and mutations. For game execution, dispatch is a shared target. Populous's
`MOVSB` helper optimization has little sampled headroom in this Majesty mission.
The two named host software presentation functions, `SW_RunCommandQueue` and
`Blit_3or4_to_3or4__inversed_rgb`, together contribute about 5% in Majesty; this
does not represent the entire guest renderer or GPU cost.

There are no measured FPS gains here. Adjacent screenshots' JIT counters increase
by 265 fresh blocks around mission A and 142 around mission B. These are two
windows from one random mission, not independent benchmark runs or a
fixed save. Menu navigation also includes manual action delays and CPU sampling,
so the session's elapsed time is not a startup benchmark. Populous's earlier 59%
startup reduction must not be transferred to Majesty without a matched test.

## Repeat with private game files

The staging tool copies the supplied runtime and Wine ZIP, verifies the runtime
manifest, packages only the main HD executable plus game data/DLLs using stored
entries, and records hashes. It refuses to reuse an output directory and leaves
the source installation intact.

```sh
python3 tools/web-cpu/prepare-majesty.py \
  --runtime project/emscripten/Build/WebCPU/profile/Jit \
  --wine /path/to/software-wine.zip \
  --game /path/to/extracted-majesty-hd \
  --out tmp/web-cpu/my-majesty-hd
python3 tools/web-cpu/cpu.py serve --port 8093
```

Open the snapshot URL printed by the tool. Accept the DX9 fallback dialog if
shown, then select Play Game → accept the player name → dismiss the quest help →
Freestyle Quests → Beginner Random. Wait for the mission and keep the camera
still. Use Chrome's CPU profiler for separate initialization and settled mission
windows, then summarize the exported profiles:

```sh
node tools/web-cpu/summarize-profile.mjs /path/to/capture.cpuprofile
```

For an automated initialization sample, the existing browser tool supports a
visible browser and a warmup interval; dismiss the fallback dialog during warmup:

```sh
node tools/web-cpu/profile-browser.mjs --warmup 60 --seconds 15 \
  --url 'http://127.0.0.1:8093/tmp/web-cpu/my-majesty-hd/boxedwine.html?root=wine.zip&app=app.zip&p=MajestyHD.exe&args=-nointro%20-nosuspend%20-dib&storage=memory&sound=false&resolution=1024x768&bpp=32' \
  --manifest tmp/web-cpu/my-majesty-hd/manifest.json \
  --out tmp/web-cpu/my-majesty-loading-profile
```

Verify the captured screenshot before labeling a profile as loading or gameplay.
The exact local diagnostic driver, recorded input actions and phase screenshots
are retained in `tmp/web-cpu/probe-majesty.mjs` and `majesty-hd-probe/`.
