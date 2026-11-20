# Pinned engine provenance

- Archive: https://languagetool.org/download/LanguageTool-6.6.zip
- Version: 6.6 (not represented as latest).
- SHA256 observed from downloaded HTTPS archive:
  `53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631`
- This is a reproducibility pin observed during development, not an upstream
  signed checksum or independent authenticity attestation.
- Actual `HTTPServer --help` inspected: no `--public`, no `--allow-origin`,
  no `--verbose`. Loopback binding must also be measured at runtime.
- Invoked with Java21; standalone README specifies Java17+.
- Package retains entire upstream distribution including COPYING and third-party
  notices. LanguageTool core LGPL2.1-or-later; bundled dictionaries/libraries
  have their own licenses. ab Proofread MIT does not relicense these components.
- Source: https://github.com/languagetool-org/languagetool/tree/v6.6
- No engine binaries are committed to the ab Proofread source repository.
