#!/bin/bash
# Run the complete block only; a partial curl download must not change packages.
{
    set -eu
    if ! { exec 3</dev/tty; } 2>/dev/null; then
        printf '%s\n' 'Run this command in an interactive terminal as your normal user.' >&2
        exit 1
    fi
    # Disable ab in this GNOME session, then remove only its Debian packages.

    if [ "$(id -u)" -eq 0 ]; then
        printf '%s\n' 'Run this as your GNOME user, without sudo.' >&2
        exit 1
    fi

    if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] && command -v gnome-extensions >/dev/null 2>&1; then
        enabled=$(gnome-extensions list --enabled)
        if printf '%s\n' "$enabled" | grep -Fxq 'ab_proofread@ab.local'; then
            gnome-extensions disable 'ab_proofread@ab.local'
        fi
    fi

    exec sudo apt remove ab-proofread ab-proofread-languagetool <&3 3<&-
}
