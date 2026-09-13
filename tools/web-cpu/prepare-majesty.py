#!/usr/bin/env python3
"""Snapshot a CPU runtime and private Majesty Gold HD files for browser diagnosis."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlencode
import zipfile


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--wine', type=Path, required=True)
    parser.add_argument('--game', type=Path, required=True, help='Extracted private HD installation')
    parser.add_argument('--out', type=Path, required=True, help='New private snapshot directory')
    args = parser.parse_args()
    runtime, game = args.runtime.resolve(), args.game.resolve()
    executable = game / 'MajestyHD.exe'
    if not executable.is_file() or not (game / 'Data').is_dir():
        parser.error('--game must contain MajestyHD.exe and Data/')
    if not zipfile.is_zipfile(args.wine):
        parser.error('--wine must be a Wine filesystem ZIP')
    manifest = json.loads((runtime / 'manifest.json').read_text())
    required = {'boxedwine.html', 'boxedwine.js', 'boxedwine.wasm', 'boxedwine-shell.js', 'boxedwine.css'}
    if not required.issubset(manifest['files']):
        parser.error('--runtime must be a complete cpu.py game build')
    for name, sha in manifest['files'].items():
        if Path(name).name != name or digest(runtime / name) != sha:
            parser.error(f'Runtime manifest mismatch: {name}')
    out = args.out.resolve()
    if out == game or game in out.parents:
        parser.error('--out must be outside the source game directory')
    out.mkdir(parents=True, exist_ok=False)
    (out / '.gitignore').write_text('*\n')
    for name in manifest['files']:
        shutil.copy2(runtime / name, out / name)
        if digest(out / name) != manifest['files'][name]:
            raise RuntimeError(f'Runtime changed while snapshotting: {name}')
    shutil.copy2(runtime / 'manifest.json', out / 'manifest.json')
    shutil.copy2(args.wine, out / 'wine.zip')
    entries = []
    executable_sha = digest(executable)
    with zipfile.ZipFile(out / 'app.zip', 'w', zipfile.ZIP_STORED) as archive:
        for path in sorted(game.rglob('*')):
            relative = path.relative_to(game)
            if not path.is_file():
                continue
            selected = relative.parts[0] in {'Data', 'DataMX', 'Music', 'Quests', 'QuestsMX'}
            selected |= len(relative.parts) == 1 and (path.name == 'MajestyHD.exe' or path.suffix.lower() == '.dll')
            if selected:
                archive.write(path, relative.as_posix())
                entries.append(relative.as_posix())
    with zipfile.ZipFile(out / 'app.zip') as archive:
        if hashlib.sha256(archive.read('MajestyHD.exe')).hexdigest() != executable_sha:
            raise RuntimeError('Game executable changed while snapshotting')
        if 'MajestyHD - Old.exe' in archive.namelist():
            raise RuntimeError('Unexpected old executable in snapshot')
    query = {'root': 'wine.zip', 'app': 'app.zip', 'p': 'MajestyHD.exe',
             'args': '-nointro -nosuspend -dib', 'resolution': '1024x768',
             'bpp': '32', 'sound': 'false', 'storage': 'memory'}
    workload = {'game': 'MajestyHD.exe', 'gameSha256': executable_sha,
                'sourceGameDirectory': str(game), 'entries': entries, 'archive': 'ZIP_STORED',
                'runtimeManifestSha256': digest(out / 'manifest.json'),
                'appSha256': digest(out / 'app.zip'), 'appBytes': (out / 'app.zip').stat().st_size,
                'wineSha256': digest(out / 'wine.zip'), 'sourceWine': str(args.wine.resolve()),
                'query': query, 'scope': 'HD executable with DIB option; D3D9 performance is not established'}
    (out / 'workload.json').write_text(json.dumps(workload, indent=2) + '\n')
    print(f'Snapshot: {out}')
    print(f'Open boxedwine.html?{urlencode(query)} through the local COOP/COEP server.')


if __name__ == '__main__':
    main()
