# Debian package lifecycle

Build on a compatible Debian/Ubuntu system with `dpkg-deb` and Python 3.10+.
Use the explicit LanguageTool 6.6 source and checksum in `engine-source.md`;
retain upstream license notices.

```sh
python3 packaging/build_deb.py --with-engine --engine-dir /path/to/LanguageTool-6.6
```

Outputs are `ab-proofread_0.1.0~dev7_all.deb` and
`ab-proofread-languagetool_6.6-1_all.deb`. The application package depends on
the latter; without `--with-engine`, it requires an already installed matching
engine package. Staging is temporary and does not write to system paths.

Install both packages through apt. The package has no maintainer scripts,
service, autostart or implicit GNOME settings changes. Remove both packages
through apt as well. An isolated dpkg lifecycle test verifies package metadata,
tracked files, upgrade replacement and purge only; it does not validate runtime
GTK/AT-SPI behavior or companion native-editor replacement.

The package is a GNOME Shell extension only; it has no standalone GTK window.
The source tree retains an experimental native editor patch, but its companion
editor adapter is not packaged. Therefore this package alone does not provide
native Replace.
