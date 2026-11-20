#!/bin/sh
# Apply only to a pristine checkout of the reviewed 50.1 upstream commit.
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
cd -- "${1:?usage: apply.sh UPSTREAM_CHECKOUT}"
test "$(git rev-parse HEAD)" = d1bc58ff790267224be1536a86e1af236a9f7ea7
test -z "$(git status --porcelain --untracked-files=normal)"
git apply --check "$here/startup.patch"
for f in editor-ab_proofread.h ab_proofread-range.h; do test ! -e "src/$f"; done
git apply "$here/startup.patch"
cp -- "$here/editor-ab_proofread.h" "$here/ab_proofread-range.h" src/
