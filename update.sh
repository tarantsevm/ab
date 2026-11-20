#!/bin/bash
# Run the complete block only; a partial curl download must not change packages.
{
    set -eu
    if ! { exec 3</dev/tty; } 2>/dev/null; then
        printf '%s\n' 'Run this command in an interactive terminal as your normal user.' >&2
        exit 1
    fi
    # Generated for a versioned release; no source build on the user's machine.
    mode='update'
    base='https://github.com/tarantsevm/ab/releases/download/v0.1.0-dev7'
    app='ab-proofread_0.1.0-dev7_all.deb'
    engine='ab-proofread-languagetool_6.6-1_all.deb'

    if [ "$(id -u)" = 0 ]; then
        printf '%s\n' 'Run as your normal GNOME user, not as root.' >&2
        exit 1
    fi
    installed() { dpkg-query -W -f='${Status} ${Version}' "$1" 2>/dev/null; }
    if [ "$mode" = update ]; then
        case $(installed ab-proofread || :) in
            'install ok installed '*) ;;
            *) printf '%s\n' 'ab is not installed. Use install-ab.sh first.' >&2; exit 1 ;;
        esac
    fi
    dir=$(mktemp -d "${TMPDIR:-/tmp}/ab-release.XXXXXX")
    trap 'rm -rf -- "$dir"' EXIT
    trap 'exit 1' HUP INT TERM
    chmod 755 "$dir"
    cd "$dir"
    get() { curl --fail --progress-bar --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --speed-limit 1024 --speed-time 45 --max-time 900 --output "$1" "$base/$1"; }
    verify() { printf '%s  %s\n' "$1" "$2" | sha256sum -c -; }
    printf '%s\n' 'Downloading ab…'
    get "$app"
    verify 'bc0c6124f34d0ed9d78a15a979a034d69fe0ed0cb9d080457e15d3968667aeca' "$app"
    set -- "./$app"
    if [ "$(installed ab-proofread-languagetool || :)" != 'install ok installed 6.6-1' ]; then
        printf '%s\n' 'Downloading LanguageTool (254 MB for this release)…'
        get "$engine"
        verify '7187088cea81f270b31860d6cd8437ca1ea3f7fd5176fdf1cf2bbedbbee1ec36' "$engine"
        set -- "./$engine" "$@"
    fi
    printf '%s\n' 'Downloads verified. Installing packages with apt…'
    sudo apt install "$@" <&3 3<&-
    printf '%s\n' 'Enable ab in GNOME Extensions after installation. To load updated code, log out and back in if needed.'
}
