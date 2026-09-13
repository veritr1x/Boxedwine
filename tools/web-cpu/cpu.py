#!/usr/bin/env python3
"""Local, reproducible Boxedwine Wasm CPU builds and test/profile artifacts."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'project/emscripten'
LOCAL = ROOT / 'tmp/web-cpu'
TARGETS = {'test': 'Test', 'testJit': 'TestJit',
           'testMultiThreaded': 'TestMultiThreaded', 'testMultiThreadedJit': 'TestMultiThreadedJit',
           'jit': 'Jit', 'multiThreadedJit': 'MultiThreadedJit', 'release': 'Release'}


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def environment():
    config = json.loads((LOCAL / 'config.json').read_text()) if (LOCAL / 'config.json').exists() else {}
    sdk = os.environ.get('EMSDK') or config.get('emsdk')
    if sdk:
        script = Path(sdk) / 'emsdk_env.sh'
        if not script.is_file():
            raise RuntimeError(f'Missing {script}')
        # Only the child environment is changed. Never log its values.
        env = json.loads(output(['bash', '-c',
            'source "$1" >/dev/null 2>&1 && python3 -c "import json,os; print(json.dumps(dict(os.environ)))"',
            'boxedwine-sdk', str(script)]))
        env['PATH'] += os.pathsep + str(Path(sdk) / 'upstream/bin')
        return env
    if not shutil.which('emcc'):
        raise RuntimeError('Run configure --emsdk /path/to/emsdk first, or activate Emscripten')
    return os.environ.copy()


def source_state():
    patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=ROOT)
    untracked = output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT).splitlines()
    return {'head': output(['git', 'rev-parse', 'HEAD'], cwd=ROOT),
            'patchSha256': hashlib.sha256(patch).hexdigest(),
            'untrackedSha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in untracked if (ROOT / name).is_file()}}


def build_dir(args):
    return PROJECT / 'Build/WebCPU' / args.mode / TARGETS[args.target]


def doctor():
    env = environment()
    report = {}
    for tool in ['emcc', 'em++', 'node', 'make', 'wasm-dis', 'llvm-objdump', 'llvm-dwarfdump', 'emsymbolizer']:
        report[tool] = shutil.which(tool, path=env['PATH'])
    report['emscripten'] = output(['emcc', '--version'], env=env).splitlines()[0]
    report['nodeVersion'] = output(['node', '--version'], env=env)
    report['chrome'] = next((str(p) for p in [
        Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        Path(shutil.which('google-chrome') or '/nonexistent'),
        Path(shutil.which('chromium') or '/nonexistent')] if p.is_file()), None)
    print(json.dumps(report, indent=2))
    return report


def build(args):
    env = environment()
    folder = build_dir(args)
    filename = 'boxedwine.js' if args.target.startswith('test') else 'boxedwine.html'
    command = ['make', '-C', str(PROJECT), args.target, f'cpus={args.jobs}',
        f'BUILD_ROOT=Build/WebCPU/{args.mode}', f'TARGET_EXEC={filename}',
        f'OPTIMIZATION_FLAGS={"-O1" if args.mode == "debug" else "-O2"}',
        f'WASM_DEBUG={int(args.mode == "debug")}',
        f'WASM_PROFILING={int(args.mode == "profile")}', 'PTHREAD_POOL_SIZE=8']
    config = {'command': command, 'emscripten': output(['emcc', '--version'], env=env),
              'node': output(['node', '--version'], env=env)}
    # Clean only this tool's selected output directory when explicitly requested.
    if args.fresh and folder.exists():
        shutil.rmtree(folder)
    marker = folder / 'configuration.json'
    if marker.exists() and json.loads(marker.read_text()) != config:
        raise RuntimeError(f'Build configuration changed. Re-run with --fresh for {folder}')
    folder.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(config, indent=2) + '\n')
    before = source_state()
    (folder / 'manifest.json').unlink(missing_ok=True)
    with (folder / 'build.log').open('w') as log:
        print(f'Building {args.target}/{args.mode}; log: {folder / "build.log"}', flush=True)
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join((folder / 'build.log').read_text().splitlines()[-30:]), file=sys.stderr)
        raise RuntimeError('Build failed')
    after = source_state()
    if before != after:
        raise RuntimeError('Sources changed during the build. Build again before using these artifacts')
    binaries = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.glob('boxedwine*') if p.is_file()}
    manifest = {'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'source': after, 'config': config, 'files': binaries}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Built {folder / filename}')


def run(args):
    if not args.target.startswith('test'):
        raise RuntimeError('run is for CPU test binaries; use serve for game builds')
    if args.profile and 'MultiThreaded' in args.target:
        raise RuntimeError('Use profile-browser.mjs for separate pthread CPU profiles')
    folder = build_dir(args)
    manifest = json.loads((folder / 'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Artifact changed after build: {name}')
    suffix = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    run_dir = LOCAL / 'runs' / suffix
    run_dir.mkdir(parents=True)
    command = ['node']
    if args.profile:
        command += ['--cpu-prof', '--cpu-prof-interval=1000', f'--cpu-prof-dir={run_dir}',
                    '--cpu-prof-name=cpu.cpuprofile']
    command += [str(folder / 'boxedwine.js')]
    if not args.full:
        command += ['-fast']
    if args.filter:
        command += ['--filter', args.filter]
    if args.list:
        command += ['--list-tests']
    timed_out = False
    with (run_dir / 'console.log').open('w') as log:
        try:
            result = subprocess.run(command, cwd=folder, env=environment(), stdout=log,
                                    stderr=subprocess.STDOUT, timeout=args.timeout)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
            log.write(f'\nCPU test run timed out after {args.timeout}s\n')
    (run_dir / 'run.json').write_text(json.dumps({'command': command, 'exitCode': exit_code,
        'timeoutSeconds': args.timeout, 'timedOut': timed_out, 'build': manifest, 'scope': 'CPU tests; not gameplay FPS',
        'profiled': args.profile}, indent=2) + '\n')
    lines = (run_dir / 'console.log').read_text().splitlines()
    print('\n'.join(lines if args.list else lines[-12:]))
    print(f'Artifacts: {run_dir}')
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    configure = commands.add_parser('configure')
    configure.add_argument('--emsdk', required=True, type=Path)
    commands.add_parser('doctor')
    tool = commands.add_parser('tool', help='Run SDK binary inspection or symbolization tools')
    tool.add_argument('name', choices=['wasm-dis', 'llvm-objdump', 'llvm-dwarfdump', 'emsymbolizer'])
    tool.add_argument('args', nargs=argparse.REMAINDER)
    for name in ['build', 'run']:
        cmd = commands.add_parser(name)
        cmd.add_argument('--mode', choices=['release', 'profile', 'debug'], default='release')
        cmd.add_argument('--target', choices=TARGETS, default='testJit')
        if name == 'build':
            cmd.add_argument('--jobs', type=int, choices=range(2, 65), default=8)
            cmd.add_argument('--fresh', action='store_true')
        else:
            cmd.add_argument('--filter')
            cmd.add_argument('--list', action='store_true')
            cmd.add_argument('--full', action='store_true')
            cmd.add_argument('--profile', action='store_true')
            cmd.add_argument('--timeout', type=float, default=300)
    serve = commands.add_parser('serve')
    serve.add_argument('--port', type=int, default=8093)
    args = parser.parse_args()
    if args.command == 'configure':
        if not (args.emsdk / 'emsdk_env.sh').is_file():
            parser.error('The SDK must contain emsdk_env.sh')
        LOCAL.mkdir(parents=True, exist_ok=True)
        (LOCAL / 'config.json').write_text(json.dumps({'emsdk': str(args.emsdk.resolve())}) + '\n')
        doctor()
    elif args.command == 'doctor':
        doctor()
    elif args.command == 'build':
        build(args)
    elif args.command == 'run':
        if not 0 < args.timeout < float('inf'):
            parser.error('--timeout must be a positive finite number of seconds')
        return run(args)
    elif args.command == 'tool':
        return subprocess.call([args.name, *args.args], env=environment())
    else:
        # Existing server supplies COOP/COEP headers for pthread tests and games.
        return subprocess.call(['node', str(PROJECT / 'server.mjs'), '--root', str(ROOT),
                                '--port', str(args.port)])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
