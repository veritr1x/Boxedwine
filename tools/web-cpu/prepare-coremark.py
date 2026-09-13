#!/usr/bin/env python3
"""Build a pinned x86 CoreMark guest and snapshot a web runtime for CPU timing."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

UPSTREAM = 'https://github.com/eembc/coremark'
REVISION = '1f483d5b8316753a742cbf5590caf5bd0a4e4777'
SOURCES = ['core_list_join.c', 'core_main.c', 'core_matrix.c', 'core_state.c', 'core_util.c']
PORT = Path(__file__).resolve().parent / 'coremark-port'


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(data)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Local EEMBC CoreMark checkout')
    parser.add_argument('--runtime', type=Path, required=True, help='cpu.py release JIT game build')
    parser.add_argument('--wine', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New ignored workload directory')
    parser.add_argument('--cc', default='i686-w64-mingw32-gcc')
    args = parser.parse_args()
    source, runtime, out = args.source.resolve(), args.runtime.resolve(), args.out.resolve()
    if out == source or source in out.parents or out == runtime or runtime in out.parents:
        parser.error('--out must be outside the input directories')
    for name in SOURCES + ['coremark.h']:
        expected = subprocess.check_output(['git', '-C', str(source), 'show', f'{REVISION}:{name}'])
        if (source / name).read_bytes() != expected:
            parser.error(f'CoreMark source differs from pinned revision: {name}')
    manifest = json.loads((runtime / 'manifest.json').read_text())
    required = {'boxedwine.html', 'boxedwine.js', 'boxedwine.wasm', 'boxedwine-shell.js', 'boxedwine.css'}
    if not required.issubset(manifest['files']):
        parser.error('--runtime must contain a complete game runtime')
    for name, sha in manifest['files'].items():
        if Path(name).name != name or digest(runtime / name) != sha:
            parser.error(f'Runtime manifest mismatch: {name}')
    if not zipfile.is_zipfile(args.wine):
        parser.error('--wine must be a Wine filesystem ZIP')
    out.mkdir(parents=True, exist_ok=False)
    (out / '.gitignore').write_text('*\n')
    cc = shutil.which(args.cc)
    if not cc:
        parser.error(f'Compiler unavailable: {args.cc}')
    flags = ['-O2', '-static', '-mwindows', '-march=pentium3', '-mtune=generic', '-fno-strict-aliasing',
             '-Wl,--no-insert-timestamp']
    input_hashes = {path: digest(path) for path in [*[source / n for n in SOURCES + ['coremark.h']], PORT / 'core_portme.c', PORT / 'core_portme.h']}
    command = [cc, *flags, '-I', str(PORT), '-I', str(source),
               '-DFLAGS_STR="' + ' '.join(flags) + '"', '-DITERATIONS=0',
               *[str(source / name) for name in SOURCES], str(PORT / 'core_portme.c'),
               '-o', str(out / 'coremark.exe')]
    with (out / 'compile.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    if any(digest(path) != sha for path, sha in input_hashes.items()):
        raise RuntimeError('Benchmark sources changed during compilation; prepare a new snapshot')
    for name in list(manifest['files']) + ['manifest.json']:
        shutil.copy2(runtime / name, out / name)
    for name, sha in manifest['files'].items():
        if digest(out / name) != sha:
            raise RuntimeError(f'Runtime changed while snapshotting: {name}')
    shutil.copy2(args.wine, out / 'wine.zip')
    with zipfile.ZipFile(out / 'app.zip', 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('coremark.exe', (2000, 1, 1, 0, 0, 0)),
                         (out / 'coremark.exe').read_bytes())
    record = {'upstream': UPSTREAM, 'revision': REVISION, 'command': command,
              'compiler': subprocess.check_output([cc, '--version'], text=True).splitlines()[0],
              'sourceSha256': {name: digest(source / name) for name in SOURCES + ['coremark.h']},
              'portSha256': {name: digest(PORT / name) for name in ['core_portme.h', 'core_portme.c']},
              'guestSha256': digest(out / 'coremark.exe'), 'appSha256': digest(out / 'app.zip'),
              'wineSha256': digest(out / 'wine.zip'), 'runtimeManifestSha256': digest(out / 'manifest.json'),
              'scope': 'Unmodified CoreMark algorithms, x86 Windows timing port, one context, 2000-byte dataset. Not gameplay FPS.',
              'timing': 'QueryPerformanceCounter elapsed wall time, reported in milliseconds; host log markers cross-check elapsed time.',
              'runRules': 'Require >=10 seconds and valid CRCs for both 0,0,0x66 and 0x3415,0x3415,0x66. Fix iterations before accepted A/B runs.'}
    (out / 'workload.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'Staged x86 CoreMark: {out}')


if __name__ == '__main__':
    main()
