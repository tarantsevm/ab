# Text Editor 50.1 pilot (not accepted)

The patch is for upstream 50.1 commit `d1bc58ff790267224be1536a86e1af236a9f7ea7` only. It is not a general Wayland write adapter. Do not substitute it for the stock editor or install it in an existing session.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -v
node --test tests/*.cjs tests/*.mjs
cc -Wall -Wextra -Werror $(pkg-config --cflags gtk4) native/gnome-text-editor/test-range.c $(pkg-config --libs gtk4) -o "$scratch/test-range"
"$scratch/test-range"
git clone --depth 1 --branch 50.1 https://github.com/GNOME/gnome-text-editor.git "$scratch/editor"
sh native/gnome-text-editor/apply.sh "$scratch/editor"
meson setup "$scratch/build" "$scratch/editor" -Ddevelopment=true --prefix="$scratch/prefix"
ninja -C "$scratch/build" src/gnome-text-editor
```

`-Ddevelopment=true` creates a distinct application ID. Build with the upstream Meson dependencies (GTK 4.22.4, GtkSourceView 5.18.0, Adwaita 1.9.1, Spelling 0.4.9, editorconfig 0.12.10 were used). Stage its binary and `data/org.gnome.TextEditor.gschema.xml` separately. Compile that copy of the schema with `glib-compile-schemas` and set `GSETTINGS_SCHEMA_DIR` only for the test session. Stage ab Proofread separately as well; route the disposable copy of the Shell extension to its staged watcher, not the installed code. Run as an ordinary user with `AB_PROOFREAD_TEXT_EDITOR=1 GTK_A11Y=atspi GDK_BACKEND=wayland GSK_RENDERER=cairo` in a private Wayland session. `--ignore-session` and a synthetic draft avoid reading any personal document. The app endpoint assumes a trusted same-login session bus, not a sandbox boundary against arbitrary processes of the same user.
