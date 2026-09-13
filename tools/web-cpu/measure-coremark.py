#!/usr/bin/env python3
"""Run a fixed x86 CoreMark workload in owned Chrome, with no CPU sampler."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
PROFILER = ROOT / 'tools/web-cpu/profile-browser.mjs'


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(data)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='prepare-coremark.py output served by cpu.py serve')
    parser.add_argument('--out', type=Path, required=True, help='New output directory')
    parser.add_argument('--iterations', type=int, required=True)
    parser.add_argument('--seed', choices=['performance', 'validation'], default='performance')
    parser.add_argument('--base-url', default='http://127.0.0.1:8093')
    parser.add_argument('--chrome', help='Chrome executable; defaults to profiler setting')
    args = parser.parse_args()
    if not 0 < args.iterations <= 0x7fffffff:
        parser.error('--iterations must be a positive signed 32-bit count')
    runtime = args.runtime.resolve()
    relative = runtime.relative_to(ROOT).as_posix()
    manifest = json.loads((runtime / 'manifest.json').read_text())
    workload = json.loads((runtime / 'workload.json').read_text())
    if digest(runtime / 'manifest.json') != workload['runtimeManifestSha256']:
        parser.error('Runtime manifest differs from the prepared workload')
    command_flags = manifest['config']['command']
    if 'WASM_PROFILING=0' not in command_flags or 'WASM_DEBUG=0' not in command_flags or any('BOXEDWINE_WASM_JIT_PROFILE' in flag for flag in command_flags):
        parser.error('Timing requires a release runtime without JIT names, counters, or debug instrumentation')
    if args.out.exists():
        parser.error('--out must be a new output directory')
    for name, wanted in manifest['files'].items():
        if Path(name).name != name or digest(runtime / name) != wanted:
            parser.error(f'Runtime manifest mismatch: {name}')
    for name, key in [('app.zip', 'appSha256'), ('wine.zip', 'wineSha256'), ('coremark.exe', 'guestSha256')]:
        if digest(runtime / name) != workload[key]:
            parser.error(f'Workload changed: {name}')
    seed = '0' if args.seed == 'performance' else '0x3415'
    query = urlencode({'root': 'wine.zip', 'app': 'app.zip', 'p': 'coremark.exe',
                       'args': f'{seed} {seed} 0x66 {args.iterations}', 'storage': 'memory',
                       'sound': 'false', 'resolution': '640x480', 'bpp': '32'})
    url = args.base_url.rstrip('/') + '/' + relative + '/boxedwine.html?' + query
    command = ['node', str(PROFILER), '--url', url, '--out', str(args.out),
               '--manifest', str(runtime / 'manifest.json'), '--headless', '--no-profile',
               '--seconds', '300', '--stop-on',
               'Correct operation validated|Errors detected|err:module:import_dll|unimplemented function']
    if args.chrome:
        command += ['--chrome', args.chrome]
    process = subprocess.run(command, cwd=ROOT)
    capture = json.loads((args.out / 'capture.json').read_text()) if (args.out / 'capture.json').exists() else {}
    rows = json.loads((args.out / 'console.json').read_text()) if (args.out / 'console.json').exists() else []
    failures = list(capture.get('failures', []))
    if process.returncode:
        failures.append(f'Browser capture exited with status {process.returncode}')
    if not capture.get('completion'):
        failures.append('Browser capture did not record benchmark completion')
    failure_path = args.out / 'failure.json'
    if failure_path.exists():
        failures.extend(json.loads(failure_path.read_text()).get('failures', []))
    text = '\n'.join(r.get('text', '') for r in rows)
    def number(pattern):
        match = re.search(pattern, text)
        return float(match[1]) if match else None
    seconds = number(r'Total time \(secs\):\s*([\d.]+)')
    throughput = number(r'Iterations/Sec\s*:\s*([\d.]+)')
    iterations = number(r'Iterations\s*:\s*(\d+)')
    crcs = dict(re.findall(r'(seedcrc|crclist|crcmatrix|crcstate|crcfinal)\s*:\s*(0x[\da-f]+)', text))
    expected = ['0xe9f5', '0xe714', '0x1fd7', '0x8e3a'] if args.seed == 'performance' else ['0x18f2', '0xe3c1', '0x0747', '0x8d84']
    crc_valid = [crcs.get(k) for k in ['seedcrc', 'crclist', 'crcmatrix', 'crcstate']] == expected
    begin = [r for r in rows if '[COREMARK] timing begin' in r.get('text', '')]
    end = [r for r in rows if '[COREMARK] timing end' in r.get('text', '')]
    host_ms = end[0]['elapsedMs'] - begin[0]['elapsedMs'] if len(begin) == len(end) == 1 else None
    clock_valid = seconds is not None and host_ms is not None and abs(host_ms - seconds * 1000) < max(250, seconds * 10)
    passed = (not failures and crc_valid
              and seconds is not None and seconds >= 10 and throughput is not None
              and iterations == args.iterations and clock_valid
              and 'Correct operation validated' in text and not re.search(r'ERROR!|Errors detected', text))
    result = {'pass': bool(passed), 'captureFailures': failures, 'seed': args.seed, 'iterations': iterations,
              'seconds': seconds, 'iterationsPerSecond': throughput, 'crcs': crcs,
              'crcValid': crc_valid, 'hostTimedLoopMs': host_ms, 'clockCrossCheck': clock_valid,
              'runtime': str(runtime), 'runtimeManifestSha256': digest(runtime / 'manifest.json'),
              'workload': workload, 'driverSha256': digest(Path(__file__)),
              'scope': 'Unprofiled x86 CoreMark timed loop through Wine and Boxedwine; not game FPS.'}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['pass', 'captureFailures', 'seconds', 'iterationsPerSecond', 'crcs', 'clockCrossCheck']}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
