"""Build the installable Blender extension ZIP from repository sources.

Run: python scripts/build_release.py
Release ZIP has a FLAT root; GitHub's auto-generated source ZIP is not installable.
"""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import ast
import hashlib
import tomllib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = tomllib.loads((ROOT / 'blender_manifest.toml').read_text(encoding='utf-8'))
VERSION = MANIFEST['version']
FILES = [
    '__init__.py', 'geometry.py', 'blender_manifest.toml',
    'assets/pylonElectricity.blend', 'README.md', 'BLENDER_TEST.md',
    'RELEASE_NOTES.md', 'LICENSE',
]


def main():
    assert MANIFEST['id'] == 'powerline_system'
    assert MANIFEST['blender_version_min'] == '5.2.0'
    for name in ('__init__.py', 'geometry.py'):
        ast.parse((ROOT / name).read_text(encoding='utf-8'))
    version_tuple = ', '.join(str(int(x)) for x in VERSION.split('.'))
    assert f'"version": ({version_tuple})' in (ROOT / '__init__.py').read_text(encoding='utf-8')
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    output = dist / f'powerline_system-{VERSION}.zip'
    with ZipFile(output, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        for path in FILES:
            source = ROOT / path
            if not source.is_file():
                raise FileNotFoundError(source)
            archive.write(source, path)
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity check failed')
        if set(archive.namelist()) != set(FILES):
            raise ValueError('Wrong archive structure')
        assert tomllib.loads(archive.read('blender_manifest.toml').decode())['version'] == VERSION
    print(f'Created: {output}')
    print(f'SHA256:  {hashlib.sha256(output.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
