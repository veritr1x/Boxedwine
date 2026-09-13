#!/usr/bin/env python3
"""Snapshot a CPU build and private Populous inputs; compile a small guest launcher."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlencode
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Directory with a cpu.py game build manifest')
    parser.add_argument('--wine', type=Path, required=True, help='Private Wine filesystem ZIP')
    parser.add_argument('--app', type=Path, required=True, help='Private ZIP with popTB.exe at its root')
    parser.add_argument('--out', type=Path, required=True, help='New snapshot directory, normally tmp/web-cpu/populous')
    parser.add_argument('--cc', default='i686-w64-mingw32-gcc')
    args = parser.parse_args()
    compiler = shutil.which(args.cc)
    if not compiler:
        parser.error('Install an i686 MinGW C compiler or supply --cc; the host SDK is not changed')
    runtime = args.runtime.resolve()
    manifest = json.loads((runtime / 'manifest.json').read_text())
    required = {'boxedwine.html', 'boxedwine.js', 'boxedwine.wasm', 'boxedwine-shell.js', 'boxedwine.css'}
    if not required.issubset(manifest['files']):
        parser.error('--runtime must be a complete game build, not a CPU test build')
    for name, sha in manifest['files'].items():
        if Path(name).name != name or digest(runtime / name) != sha:
            parser.error(f'Runtime manifest mismatch: {name}')
    for path in [args.wine, args.app]:
        if not zipfile.is_zipfile(path):
            parser.error(f'Not a ZIP archive: {path}')
    with zipfile.ZipFile(args.app) as archive:
        if 'poptb.exe' not in {name.lower() for name in archive.namelist()}:
            parser.error('App ZIP must contain the software popTB.exe at its root')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / '.gitignore').write_text('*\n') # Never accidentally publish private input snapshots.
    source = ROOT / 'tools/web-cpu/workloads/populous-start.c'
    command = [compiler, '-Os', '-Wall', '-Wextra', '-Werror', '-static-libgcc',
               '-Wl,--no-insert-timestamp', str(source), '-o', str(out / 'populous-start.exe'), '-ladvapi32']
    subprocess.run(command, check=True)
    with zipfile.ZipFile(out / 'launch.zip', 'w') as archive:
        entry = zipfile.ZipInfo('tmp/populous-start.exe', (1980, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, (out / 'populous-start.exe').read_bytes())
    for name in manifest['files']:
        shutil.copy2(runtime / name, out / name)
        if digest(out / name) != manifest['files'][name]:
            raise RuntimeError(f'Runtime changed while snapshotting: {name}')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    inputs = {}
    for name, path in [('wine.zip', args.wine), ('app.zip', args.app)]:
        shutil.copy2(path, out / name)
        inputs[name] = {'source': str(path.resolve()), 'sha256': digest(out / name),
                        'bytes': (out / name).stat().st_size}
    workload = {'inputs': inputs, 'runtimeManifestSha256': digest(out / 'manifest.json'),
        'launcherSourceSha256': digest(source), 'launcherSha256': digest(out / 'populous-start.exe'),
        'overlaySha256': digest(out / 'launch.zip'), 'compileCommand': command,
        'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
        'game': 'popTB.exe', 'registry': 'regs.cmd values, one process',
        'resolution': '640x480', 'bpp': 32, 'sound': False}
    (out / 'workload.json').write_text(json.dumps(workload, indent=2) + '\n')
    query = urlencode({'root': 'wine.zip', 'app': 'app.zip', 'overlay': 'launch.zip',
                       'p': 'Z:\\tmp\\populous-start.exe', 'storage': 'memory', 'sound': 'false',
                       'resolution': '640x480', 'bpp': '32'})
    print(f'Snapshot: {out}')
    print(f'Open boxedwine.html?{query} through the local COOP/COEP server.')


if __name__ == '__main__':
    main()
