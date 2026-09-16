#!/bin/sh
set -eu

# Deliberately separate from scripts/release.py: this runtime is mutable,
# dirty-source-capable, and never a release or rollback authority.
repo_root=/home/josh/src/lulu
runtime=/opt/lulu/dev-current
dropin_root=/etc/systemd/system
session_dropin="$dropin_root/lulu-session@.service.d/dev-runtime.conf"
consoled_dropin="$dropin_root/lulu-consoled.service.d/dev-runtime.conf"
acquisition_dropin="$dropin_root/lulu-acquisition.service.d/dev-runtime.conf"
acquisition_unit="$dropin_root/lulu-acquisition.service"

if [ "$(hostname)" != lulu ] || [ "$(CDPATH= cd -- "$repo_root" && pwd)" != "$repo_root" ]; then
    echo "dev runtime must be refreshed on canonical Lulu from $repo_root" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

refresh() {
    head=$(git -C "$repo_root" rev-parse HEAD)
    branch=$(git -C "$repo_root" branch --show-current)
    status=$(git -C "$repo_root" status --porcelain --untracked-files=all)
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    staging=/opt/lulu/.dev-staging-$$
    rm -rf "$staging"
    mkdir -p "$staging/bin"
    for directory in src ui scripts config packaging native; do
        cp -a "$repo_root/$directory" "$staging/$directory"
    done
    cp -a "$repo_root/src" "$staging/lib"
    cp "$repo_root/packaging/lulu-vt" "$staging/bin/lulu-vt"
    cp "$repo_root/deploy/payload/bin/verify-mudos.sh" "$staging/bin/verify-mudos.sh"
    LULU_INSTALL_ROOT="$staging" "$staging/scripts/build-lulu-shell.sh" "$staging/bin/lulu-shell"
    chmod +x "$staging/bin"/* "$staging/scripts"/*
    install -m 0644 "$staging/packaging/lulu-acquisition.service" "$acquisition_unit"
    dirty=false
    [ -n "$status" ] && dirty=true
    cat > "$staging/NON_PROMOTABLE" <<EOF
development-runtime=true
promotable=false
source=$repo_root
head=$head
branch=$branch
dirty=$dirty
refreshed=$stamp
EOF
    rm -rf "$runtime"
    mv "$staging" "$runtime"
    mkdir -p "$(dirname "$session_dropin")" "$(dirname "$consoled_dropin")" "$(dirname "$acquisition_dropin")"
    cat > "$session_dropin" <<EOF
[Service]
Environment=LULU_INSTALL_ROOT=$runtime
Environment=PYTHONPATH=$runtime/lib
Environment=LULU_SHELL_EXECUTABLE=$runtime/bin/lulu-shell
Environment=LULU_UI_FILE=$runtime/ui/ConsoleShell.qml
EOF
    cat > "$consoled_dropin" <<EOF
[Service]
Environment=LULU_INSTALL_ROOT=$runtime
Environment=PYTHONPATH=$runtime/lib
Environment=LULU_SHELL_EXECUTABLE=$runtime/bin/lulu-shell
Environment=LULU_UI_FILE=$runtime/ui/ConsoleShell.qml
EOF
    cat > "$acquisition_dropin" <<EOF
[Service]
Environment=PYTHONPATH=$runtime/lib
EOF
    systemctl daemon-reload
    systemctl restart lulu-acquisition.service lulu-consoled.service lulu-session@2.service
    echo "refreshed non-promotable dev runtime: $runtime"
}

immutable() {
    rm -f "$session_dropin" "$consoled_dropin" "$acquisition_dropin" "$acquisition_unit"
    systemctl daemon-reload
    systemctl restart lulu-consoled.service lulu-session@2.service
    echo "restored immutable runtime: $(readlink -f /opt/lulu/current)"
}

case "${1:-}" in
    refresh) refresh ;;
    immutable|restore) immutable ;;
    *) echo "usage: $0 refresh|immutable" >&2; exit 2 ;;
esac
