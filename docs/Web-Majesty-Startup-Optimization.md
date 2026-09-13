# Majesty HD startup: consolidate timestamp lookups

This isolated change reduces median Majesty Gold HD startup from **150.155 to 86.272 seconds (42.5%)** across three alternating runs per arm. Every run reaches the visible menu and successfully opens the player-name dialog.

Majesty Gold HD 1.5.2.28 repeatedly asks Wine for file metadata during asset initialization. Each guest stat previously requested access, modification and change times through separate file-node accessors. On Emscripten, a native file with no timestamp overrides required six host stats for these timestamps; a ZIP-only file required nine because the nanosecond fallbacks repeated the failed native lookup.

`FsNode::getTimes()` returns all six timestamp fields together. `FsFileNode` now issues at most one host stat for that timestamp group, then applies the existing ZIP fallback and explicit timestamp overrides. Two active overrides avoid the host timestamp lookup entirely. No result survives the current request. The change covers stat64, lstat64, fstat64, fstatat64 and statx. File length, mode, xattrs and their existing lookups are outside this change; fstat still obtains length through the open file descriptor.

Semantics retained: hard-link shared overrides, nanosecond fractions, rename and write visibility, archive-to-native copy-on-write, native zero-mtime fallback to ctime, and Boxedwine's existing exposure of modification time as guest ctime. Virtual/memory/device nodes retain their existing timestamp accessors through the base implementation.

## Matched measurement

On 2026-09-13, Apple M5 Max / 48 GiB, Chrome 152.0.7977.83, Emscripten 6.0.9, single-threaded JIT `-O2` with profile function names:

| Configuration | Menu runs (seconds) | Median menu | Median name dialog |
| --- | --- | ---: | ---: |
| Before timestamp consolidation | 149.267, 153.175, 150.155 | 150.155 s | 151.475 s |
| One timestamp snapshot per stat | 86.463, 86.272, 85.395 | 86.272 s | 87.590 s |

Median time saved: **63.883 seconds**. Three alternating baseline/candidate pairs, preceded by one excluded harness pilot. Fresh owned headless Chrome each time, memory storage, local warm filesystem, no active CPU sampler, no compilers or other owned game benchmarks. Both arms use the same ZIP_STORED MajestyHD.exe archive and software Wine ZIP; the old executable is excluded. Resolution 1024x768, bpp32, emulator sound disabled, arguments `-nointro -nosuspend -dib`. The DX9 initialization dialog is automatically accepted in both arms; these measurements use the built-in fallback renderer.

The endpoint is navigation to the first screenshot matching the static menu button bar. The driver then clicks Play Game and requires the name-entry dialog to appear. Screenshots are checked approximately once per second, so the recorded detection times are upper bounds with about one screenshot interval of resolution. The previous nonmatching observation is retained. CPU sampling and mission checks run separately from this timing comparison.

References were selected before timing from the previous diagnostic session. At fixed 1280x1000 viewport, RGB pixels are sampled every six pixels within predefined screen regions. More than 97% must differ by at most 12 per channel. The matcher identified the three known states and rejected black/loading/mission and other-state images before accepted runs. Private reference images, all captured milestone screenshots, comparison scores, input actions, console logs and harness sources remain under ignored `tmp/web-cpu/`. The public record contains their hashes and timing values, not game assets.

The baseline runtime comes from `f57fc0a7a130c2d9d9ae0ed9eec438dfd3560adf`; the candidate is the code in commit `40e00802` on `perf/metadata-startup`. The [measurement record](benchmarks/2026-09-13-metadata-startup.json) includes exact source/runtime/input hashes, every run, test manifests and separate diagnostic samples.

Local timing command (existing private workload snapshots and reference images):

```sh
node tmp/web-cpu/measure-majesty.mjs \
  tmp/web-cpu/my-new-measurement tmp/web-cpu/majesty-hd-metadata
```

Use a new output path each time. Alternate with `tmp/web-cpu/majesty-hd-verified` for the baseline. The retained local driver imports the existing sibling Playwright installation and uses Python/Pillow for private reference-image matching; these are additional local dependencies, not part of the dependency-free CDP profiler. See [staging instructions](Web-Majesty-HD-Profile.md#repeat-with-private-game-files) for constructing a snapshot from a supplied game installation. No private game files or screenshots are committed.

## Separate profile and mission check

The candidate's separate black-screen initialization sample attributes 24.06% of all sampled time to path lookup (previous diagnostic windows: 39.86–40.47%). Of the candidate's total sampled time, 15.24% is lookup under `getXAttrResult` and 8.82% under `FsFileNode::getTimes`. Those windows are from different points within initialization; their relative sample shares diagnose remaining work, while the unprofiled table above measures the gain. The next startup candidate is the repeated extended-attribute existence check, with missing-file and mutation semantics to verify before changing it.

The candidate enters a rendered Random (Beginner) mission. Treasury advances from 20,000 to 20,060 to 20,141 over the retained screenshots; the day display remains 0. Two separate 15-second mission samples attribute 24.41% and 24.93% to JIT entry/next-block dispatch, with negligible metadata lookup. These are samples of one random mission, not a matched gameplay A/B test. JIT dispatch remains the next game execution target; no game-frame or simulation-throughput improvement is claimed here.

## Validation

- All 770 single-threaded JIT fast tests pass.
- All 750 single-threaded interpreter fast tests pass.
- Rebuilding after the final test-fixture formatting change reproduces every measured game and tested JIT/interpreter artifact hash exactly.
- New timestamp compatibility tests cover stat-family outputs, fractional timestamps, aliases, rename, writes, external timestamp mutations and ZIP copy-on-write.
- MT, native MSVC, audio, persistence, D3D9/WebGPU performance and sustained gameplay are outside this validation. Existing MT failures remain unresolved.

This is a startup optimization. It does not establish an FPS improvement or remove the shared JIT-dispatch hotspot during gameplay.
