#!/usr/bin/python3
"""Build ab Proofread Debian package."""
from pathlib import Path
import argparse
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
APP_VERSION = '0.1.0~dev7'
ENGINE_VERSION = '6.6-1'


def build(stage, output):
    payload = [p for p in stage.rglob('*') if p.is_file() and 'DEBIAN' not in p.parts]
    size_kib = (sum(p.stat().st_size for p in payload) + 1023) // 1024
    control = stage / 'DEBIAN/control'
    control.write_text(control.read_text() + f'Installed-Size: {size_kib}\n')
    for path in stage.rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o644)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(output)], check=True)


def put(stage, name, content):
    dest = stage / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine-dir', type=Path,
                        help='verified, extracted LanguageTool 6.6 distribution (requires --with-engine)')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--with-engine', action='store_true',
                        help='also build the separate local LanguageTool package')
    args = parser.parse_args()
    if not args.with_engine and args.engine_dir:
        parser.error('--engine-dir requires --with-engine')
    if args.with_engine and not args.engine_dir:
        parser.error('--with-engine requires --engine-dir')
    if args.engine_dir and not (args.engine_dir / 'languagetool-server.jar').is_file():
        parser.error('engine directory must contain languagetool-server.jar')
    if args.engine_dir and (not (args.engine_dir / 'COPYING.txt').is_file() or
                            not any((args.engine_dir / 'third-party-licenses').glob('*.txt'))):
        parser.error('engine directory must retain upstream license notices')

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ab-proofread-build-') as tmp:
        stage = Path(tmp) / 'app'
        put(stage, 'DEBIAN/control', f'''Package: ab-proofread
Version: {APP_VERSION}
Architecture: all
Maintainer: ab Proofread contributors <ab@users.noreply.github.com>
Depends: gnome-shell (>= 50), gnome-shell (<< 51), python3 (>= 3.10), python3-gi, gir1.2-atspi-2.0, at-spi2-core, ab-proofread-languagetool (>= 6.6)
Section: utils
Priority: optional
Description: GNOME Shell local proofreading (development preview)
 Contextual selection check and top-bar status using a local LanguageTool engine.
''')
        shutil.copytree(ROOT / 'ab_proofread', stage / 'usr/share/ab-proofread/ab_proofread',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shell_extension = 'ab_proofread@ab.local'
        shutil.copytree(ROOT / 'extensions' / shell_extension,
                        stage / 'usr/share/gnome-shell/extensions' / shell_extension)

        for name in ('LICENSE', 'README.md', 'README.ru.md', 'CHANGELOG.md'):
            dest = stage / 'usr/share/doc/ab-proofread' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        shutil.copytree(ROOT / 'docs', stage / 'usr/share/doc/ab-proofread/docs')
        build(stage, out / f'ab-proofread_{APP_VERSION}_all.deb')

        if args.with_engine:
            engine = Path(tmp) / 'engine'
            shutil.copytree(args.engine_dir, engine / 'usr/share/ab-proofread-languagetool')
            put(engine, 'DEBIAN/control', f'''Package: ab-proofread-languagetool
Version: {ENGINE_VERSION}
Architecture: all
Maintainer: ab Proofread contributors <ab@users.noreply.github.com>
Depends: openjdk-21-jre-headless
Section: text
Priority: optional
Description: Unmodified LanguageTool 6.6 local engine for ab Proofread
 Upstream distribution with all bundled license notices, no cloud service.
''')
            build(engine, out / f'ab-proofread-languagetool_{ENGINE_VERSION}_all.deb')


if __name__ == '__main__':
    main()
