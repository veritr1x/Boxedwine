# Majesty HD startup: faster attribute existence checks

This second isolated optimization reduces median Majesty Gold HD startup from **86.402 to 75.883 seconds (12.2%)** across three alternating runs per arm. Every run reaches the visible menu and successfully opens the player-name dialog.

This follows the [timestamp consolidation](Web-Majesty-Startup-Optimization.md). The baseline already contains that optimization. Only the existence check in `Fs::getXAttr` changes here; timestamp handling, JIT execution, file reads, game data and graphics remain outside this change.

## Change

Boxedwine stores the supported `user.DOSATTRIB` and `user.WINEREPARSE` attributes in sidecar files. Wine repeatedly queries attributes which are absent while Majesty indexes assets. The previous startup profile attributed 15.24% of sampled time to path lookup under `getXAttrResult` after timestamp consolidation.

The single-threaded web path now walks the current Emscripten filesystem nodes for simple absolute paths. It uses `FS.lookupNode`, retaining permission checks and backend/name lookup behavior, and stops on the same filesystem errors as an existence check. It avoids rebuilding and normalizing the resolved path at every component. [Emscripten's general lookup API](https://emscripten.org/docs/api_reference/Filesystem-API.html#FS.lookupPath) returns both a node and a resolved path; this existence check needs only the node.

There is no cache between requests. Symlinks, mount points, relative paths, dot components, repeated slashes and trailing slashes fall back to the existing libc `access(F_OK)` path. Native and pthread builds keep the previous implementation. The shortcut is validated against the actual Emscripten 6.0.9 filesystem in both interpreter and JIT test builds. `FS.lookupNode` is an internal runtime dependency, so SDK upgrades must retain the path-equivalence test.

## Matched measurement

On 2026-09-13, Apple M5 Max / 48 GiB, Chrome 152.0.7977.83, Emscripten 6.0.9, single-threaded JIT `-O2` with profile function names:

| Configuration | Menu runs (seconds) | Median menu | Median name dialog |
| --- | --- | ---: | ---: |
| Timestamp consolidation baseline | 85.265, 86.402, 86.426 | 86.402 s | 87.724 s |
| Faster attribute existence check | 75.883, 75.844, 75.924 | 75.883 s | 77.177 s |

Median time saved: **10.519 seconds**. All six runs pass the menu and input checks with zero page exceptions. Every detected menu and name-dialog reference region matches all sampled points within the configured tolerance. The [measurement record](benchmarks/2026-09-13-xattr-startup.json) contains exact source/runtime/input hashes, each timing run, test manifests and separate diagnostic samples.

### Method

Three alternating baseline/candidate pairs, fresh owned headless Chrome per run, no CPU sampler or compilers during timing, local warm filesystem. Same `MajestyHD.exe` 1.5.2.28, identical ZIP_STORED game and Wine inputs, 1024x768 at 32 bpp, memory storage, disabled emulator sound, arguments `-nointro -nosuspend -dib`. Both arms accept the same DX9 initialization fallback dialog. D3D9/WebGPU performance is not measured.

The unchanged driver checks the same private screenshot reference regions approximately once per second. The endpoint is the visible menu button bar, followed by a successful Play Game transition to the player-name dialog. It records the previous nonmatching observation, screenshots, all match scores, console output and input actions. These are detection times with roughly one screenshot interval of resolution, including capture/matching overhead. No timing results are taken from the separate diagnostic CPU-profile session.

The baseline runtime is commit `40e00802` (Wasm `f22205a1043cd93122d7341ff056c2d919b98e99cffef953d6de60b5b88357d9`); the candidate is `18f2b46a` (Wasm `0af155a80f3459b2635d786cb966e2c1b20b38097a06388742e8a0ac9d9028a5`). The baseline retains its original precommit manifest; the previous measurement record verifies byte-identical runtime artifacts after the timestamp change was committed. Private snapshots are `tmp/web-cpu/majesty-hd-metadata` and `tmp/web-cpu/majesty-hd-xattr`. Use the same retained local driver with a new output path:

```sh
node tmp/web-cpu/measure-majesty.mjs \
  tmp/web-cpu/my-new-xattr-run tmp/web-cpu/majesty-hd-xattr
```

See the [previous measurement's reproduction requirements](Web-Majesty-Startup-Optimization.md#matched-measurement) for the local Playwright/Pillow dependencies and private reference images. Raw accepted captures are under `tmp/web-cpu/xattr-matched/`. The public measurement record contains hashes and results, not game assets or screenshots.

## Separate CPU profile and mission check

A separate diagnostic run captures the same black-screen initialization phase about 34–49 seconds after navigation, then enters a Random (Beginner) mission. It is excluded from the timing table.

| Sample window | General path lookup/normalization | New attribute-existence helper | JIT entry/next-block dispatch |
| --- | ---: | ---: | ---: |
| Initialization, 15 seconds | 10.32% | 7.89% | 20.78% |
| Mission A, 15 seconds | 0.00% | 0.00% | 26.49% |
| Mission B, 15 seconds | 0.01% | 0.00% | 28.96% |

These are self-time shares of all samples, including idle time. General path lookup in the initialization sample is now entirely under timestamp handling. The new attribute-existence helper still costs time: it replaces the previous general lookup work under `getXAttrResult`, whose earlier diagnostic sample share was 15.24%. The windows and executed work differ, so sample shares explain the remaining costs; the unprofiled matched runs establish the startup improvement.

Retained mission screenshots show a rendered world with treasury advancing **20,000 → 20,025 → 20,050**, while the day display remains 0. The random layout differs from the earlier candidate mission. This is a short running-mission smoke, not a gameplay speed comparison. No page exceptions occurred; existing guest audio-decoder errors remain with emulator sound disabled.

The next game CPU target is JIT entry/next-block dispatch. It remains prominent in both mission windows while metadata lookup is negligible. A separate diagnostic counter build and a repeatable saved-game or demo workload are needed before changing dispatch and measuring game throughput. This pass contains no JIT change or FPS result.

## Compatibility coverage

All 772 ST JIT and 752 ST interpreter fast tests pass. The tested source manifests exactly match the candidate commit via parent HEAD and patch SHA256. New tests check both supported attributes, missing/empty/binary values, length queries, null and short buffers, output canaries, external sidecar creation/deletion, hard-link aliases and rename. The path test compares directly with libc `access`, including ENOTDIR, parent permissions, directory replacement, Unicode names and names matching object prototype members. Native symlink and mounted-filesystem attribute reads exercise the fallback end to end. This does not establish MT behavior, persisted IDBFS performance, audio, save persistence or gameplay FPS.

Results cover three alternating pairs on one host/browser and the built-in graphics fallback. Mounted filesystem paths deliberately retain libc lookup; persisted IDBFS performance is unmeasured. Existing MT test failures remain unresolved.
