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
session_unit="$dropin_root/lulu-session@.service"
consoled_unit="$dropin_root/lulu-consoled.service"
target_unit="$dropin_root/lulu.target"
osk_unit="$dropin_root/lulu-osk@.service"
questarr_reconcile_unit="$dropin_root/lulu-questarr-reconcile.service"
inputplumber_hotplug_unit="$dropin_root/lulu-inputplumber-hotplug.service"
transmission_config_unit="$dropin_root/lulu-transmission-config.service"
sunshine_user_config=/home/lulu/.config/sunshine
sunshine_user_units=/home/lulu/.config/systemd/user

if [ "$(hostname)" != lulu ] || [ "$(CDPATH= cd -- "$repo_root" && pwd)" != "$repo_root" ]; then
    echo "dev runtime must be refreshed on canonical Lulu from $repo_root" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

refresh() {
    logger -t lulu-runtime "event=refresh-start source=$repo_root target=$runtime" 2>/dev/null || true
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
    install -m 0644 "$staging/packaging/lulu-session@.service" "$session_unit"
    install -m 0644 "$staging/packaging/lulu-consoled.service" "$consoled_unit"
    install -m 0644 "$staging/packaging/lulu.target" "$target_unit"
    sed "s#/opt/lulu/current#/opt/lulu/dev-current#g" \
        "$staging/packaging/lulu-osk@.service" > "$osk_unit"
    sed "s#/opt/lulu/current#/opt/lulu/dev-current#g" \
        "$staging/packaging/lulu-questarr-reconcile.service" > "$questarr_reconcile_unit"
    install -m 0644 "$staging/packaging/udev/80-lulu-osk.rules" \
        /etc/udev/rules.d/80-lulu-osk.rules
    install -m 0644 "$staging/packaging/udev/81-lulu-gamepad-hotplug.rules" \
        /etc/udev/rules.d/81-lulu-gamepad-hotplug.rules
    install -m 0644 "$staging/packaging/lulu-inputplumber-hotplug.service" \
        "$inputplumber_hotplug_unit"
    install -m 0644 "$staging/packaging/lulu-transmission-config.service" \
        "$transmission_config_unit"
    chmod +x "$staging/scripts/provision-appliance-services.sh" \
        "$staging/scripts/provision-acquisition-services.sh" \
        "$staging/scripts/provision-nzbget.sh" "$staging/scripts/provision-transmission.sh" \
        "$staging/scripts/configure-acquisition-firewall.sh"
    LULU_SOURCE_ROOT="$repo_root" LULU_SECRET_HELPER_ROOT="$staging" \
        LULU_PROVIDER_CONFIG_USER=lulu LULU_INSTALL_ROOT="$staging" \
        LULU_SERVICE_ROOT="$runtime" "$staging/scripts/provision-appliance-services.sh"
    "$staging/scripts/configure-acquisition-firewall.sh"
    install -D -m 0644 "$staging/packaging/sunshine-dev.conf" \
        "$sunshine_user_config/sunshine.conf"
    install -D -m 0644 "$staging/packaging/sunshine-dev-apps.json" \
        "$sunshine_user_config/apps.json"
    chmod +x "$staging/scripts/configure-dev-sunshine-firewall.sh"
    "$staging/scripts/configure-dev-sunshine-firewall.sh"
    install -D -m 0644 "$staging/packaging/lulu-sunshine-dev.service" \
        "$sunshine_user_units/lulu-sunshine-dev.service"
    mkdir -p "$sunshine_user_units/default.target.wants"
    chown -R lulu:lulu /home/lulu/.config/sunshine "$sunshine_user_units/lulu-sunshine-dev.service"
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/49-lulu-network.rules" \
        /etc/polkit-1/rules.d/49-lulu-network.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/50-lulu-storage.rules" \
        /etc/polkit-1/rules.d/50-lulu-storage.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/51-lulu-nzbget.rules" \
        /etc/polkit-1/rules.d/51-lulu-nzbget.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/52-lulu-acquisition.rules" \
        /etc/polkit-1/rules.d/52-lulu-acquisition.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/53-lulu-questarr-reconcile.rules" \
        /etc/polkit-1/rules.d/53-lulu-questarr-reconcile.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/54-lulu-transmission.rules" \
        /etc/polkit-1/rules.d/54-lulu-transmission.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/55-lulu-transmission-config.rules" \
        /etc/polkit-1/rules.d/55-lulu-transmission-config.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/56-lulu-session-restart.rules" \
        /etc/polkit-1/rules.d/56-lulu-session-restart.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/57-lulu-provider-install.rules" \
        /etc/polkit-1/rules.d/57-lulu-provider-install.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/58-lulu-recovery-power.rules" \
        /etc/polkit-1/rules.d/58-lulu-recovery-power.rules
    install -D -m 0644 "$staging/packaging/polkit-1/rules.d/59-lulu-initial-password.rules" \
        /etc/polkit-1/rules.d/59-lulu-initial-password.rules
    install -D -m 0755 "$staging/packaging/mudos-set-initial-password" \
        /usr/libexec/mudos-set-initial-password
    install -D -m 0755 "$staging/packaging/mudos-provider-install" \
        "$staging/bin/mudos-provider-install"
    install -D -m 0644 "$staging/packaging/avahi/mudos-http.service" \
        /etc/avahi/services/mudos-http.service
    install -D -m 0644 "$staging/ui/Onboarding.qml" "$runtime/ui/Onboarding.qml"
    install -D -m 0644 "$staging/ui/Recovery.qml" "$runtime/ui/Recovery.qml"
    sed "s#/opt/lulu/current#/opt/lulu/dev-current#g" \
        "$staging/packaging/lulu-provider-install@.service" \
        > /etc/systemd/system/lulu-provider-install@.service
    systemctl reload polkit.service 2>/dev/null || true
    # InputPlumber consumes system device definitions, not the mutable runtime
    # tree. Install the repo-owned generic policy on every refresh so an old
    # receiver-specific file cannot survive a development deployment.
    "$staging/scripts/provision-inputplumber-gamepads.py" \
        /etc/inputplumber/devices.d/lulu-composite.yaml
    udevadm control --reload-rules
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
[Unit]
Wants=lulu-osk@%i.service

[Service]
Environment=LULU_INSTALL_ROOT=$runtime
Environment=PYTHONPATH=$runtime/lib
Environment=LULU_SHELL_EXECUTABLE=$runtime/bin/lulu-shell
Environment=LULU_UI_FILE=$runtime/ui/ConsoleShell.qml
Environment=LULU_GUIDE_EXECUTABLE=$runtime/bin/mudos-guide
Environment=LULU_GUIDE_UI_FILE=$runtime/ui/MudosGuide.qml
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
Environment=LULU_INSTALL_ROOT=$runtime
EOF
    systemctl daemon-reload
    systemctl disable lulu-acquisition.service lulu-consoled.service >/dev/null 2>&1 || true
    # Provider reconciliation is opt-in and readiness-gated by Consoled.
    # A runtime refresh must never start Questarr merely because its unit exists.
    systemctl disable lulu-questarr-reconcile.service >/dev/null 2>&1 || true
    systemctl restart lulu-admin.service
    # Provisioning installs the recovery units before the new runtime tree is
    # swapped into place. Restart the independent control plane now so it
    # imports the just-published dev-current source, not the previous tree.
    systemctl restart mudos-recovery.service
    sudo -u lulu XDG_RUNTIME_DIR=/run/user/958 \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus \
        systemctl --user daemon-reload
    # KMS capture and Gamescope share the physical connector, but Gamescope
    # must acquire DRM master first.  A refresh restarts the presentation
    # session, so release Sunshine before that restart and bring it back only
    # after Gamescope has been launched.
    sudo -u lulu XDG_RUNTIME_DIR=/run/user/958 \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus \
        systemctl --user stop lulu-sunshine-dev.service || true
    systemctl restart inputplumber.service
    systemctl restart lulu-session@2.service
    sudo -u lulu XDG_RUNTIME_DIR=/run/user/958 \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus \
        systemctl --user enable --now lulu-sunshine-dev.service
    logger -t lulu-runtime "event=refresh-complete target=$runtime head=$head" 2>/dev/null || true
    echo "refreshed non-promotable dev runtime: $runtime"
}

immutable() {
    rm -f "$session_dropin" "$consoled_dropin" "$acquisition_dropin"
    # Restore deployment-owned units from the active immutable release. The
    # old implementation deleted these files, leaving lulu.target with a
    # dangling OSK link and leaving the shell without Acquisitiond on reboot.
    immutable_root=$(CDPATH= cd -- "$(readlink -f /opt/lulu/current)" && pwd)
    install -m 0644 "$immutable_root/packaging/lulu-acquisition.service" "$acquisition_unit"
    install -m 0644 "$immutable_root/packaging/lulu-session@.service" "$session_unit"
    install -m 0644 "$immutable_root/packaging/lulu-consoled.service" "$consoled_unit"
    install -m 0644 "$immutable_root/packaging/lulu.target" "$target_unit"
    install -m 0644 "$immutable_root/packaging/lulu-osk@.service" "$osk_unit"
    install -m 0644 "$immutable_root/packaging/udev/80-lulu-osk.rules" \
        /etc/udev/rules.d/80-lulu-osk.rules
    install -D -m 0644 "$immutable_root/packaging/polkit-1/rules.d/49-lulu-network.rules" \
        /etc/polkit-1/rules.d/49-lulu-network.rules
    install -D -m 0644 "$immutable_root/packaging/polkit-1/rules.d/50-lulu-storage.rules" \
        /etc/polkit-1/rules.d/50-lulu-storage.rules
    install -D -m 0644 "$immutable_root/packaging/polkit-1/rules.d/56-lulu-session-restart.rules" \
        /etc/polkit-1/rules.d/56-lulu-session-restart.rules
    install -D -m 0644 "$immutable_root/packaging/polkit-1/rules.d/57-lulu-provider-install.rules" \
        /etc/polkit-1/rules.d/57-lulu-provider-install.rules
    install -D -m 0644 "$immutable_root/packaging/polkit-1/rules.d/58-lulu-recovery-power.rules" \
        /etc/polkit-1/rules.d/58-lulu-recovery-power.rules
    install -D -m 0644 "$immutable_root/packaging/polkit-1/rules.d/59-lulu-initial-password.rules" \
        /etc/polkit-1/rules.d/59-lulu-initial-password.rules
    install -D -m 0755 "$immutable_root/packaging/mudos-set-initial-password" \
        /usr/libexec/mudos-set-initial-password
    install -D -m 0644 "$immutable_root/packaging/avahi/mudos-http.service" \
        /etc/avahi/services/mudos-http.service
    install -m 0644 "$immutable_root/packaging/lulu-provider-install@.service" \
        /etc/systemd/system/lulu-provider-install@.service
    udevadm control --reload-rules
    systemctl daemon-reload
    systemctl disable lulu-acquisition.service lulu-consoled.service >/dev/null 2>&1 || true
    systemctl restart lulu-session@2.service
    echo "restored immutable runtime: $(readlink -f /opt/lulu/current)"
}

case "${1:-}" in
    refresh) refresh ;;
    immutable|restore) immutable ;;
    *) echo "usage: $0 refresh|immutable" >&2; exit 2 ;;
esac
