#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) -ne 0 ]]; then exec sudo -n "$0" "$@"; fi
root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
service_root=${LULU_SERVICE_ROOT:-$root}
recovery_token_file=/etc/lulu/mudos-recovery-token
if [[ ! -s "$recovery_token_file" ]]; then
    token_temp=$(mktemp /etc/lulu/.mudos-recovery-token.XXXXXX)
    recovery_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    printf 'LULU_RECOVERY_TOKEN=%s\n' "$recovery_token" > "$token_temp"
    unset recovery_token
    chown root:lulu "$token_temp"
    chmod 0640 "$token_temp"
    if [[ ! -e "$recovery_token_file" ]]; then
        mv "$token_temp" "$recovery_token_file"
    else
        rm -f "$token_temp"
    fi
fi
sed "s#/opt/lulu/current#$service_root#g" "$root/packaging/lulu-admin.service" > /etc/systemd/system/lulu-admin.service
if [[ ! -x "$service_root/bin/mudos-provider-install" ]]; then
    echo "immutable runtime is missing bin/mudos-provider-install: $service_root" >&2
    exit 1
fi
sed "s#/opt/lulu/current#$service_root#g" "$root/packaging/lulu-provider-install@.service" \
    > /etc/systemd/system/lulu-provider-install@.service
install -D -m 0644 "$root/packaging/polkit-1/rules.d/57-lulu-provider-install.rules" \
    /etc/polkit-1/rules.d/57-lulu-provider-install.rules
install -D -m 0644 "$root/packaging/polkit-1/rules.d/61-lulu-dolphin-bluetooth.rules" \
    /etc/polkit-1/rules.d/61-lulu-dolphin-bluetooth.rules
install -D -m 0644 "$root/packaging/polkit-1/rules.d/60-lulu-recovery.rules" \
    /etc/polkit-1/rules.d/60-lulu-recovery.rules
for unit in mudos-recovery.service mudos-recovery-guard.service mudos-recovery-ui.service; do
    sed "s#/opt/lulu/current#$service_root#g" "$root/packaging/$unit" \
        > "/etc/systemd/system/$unit"
done
install -D -m 0644 "$root/packaging/polkit-1/rules.d/58-lulu-recovery-power.rules" \
    /etc/polkit-1/rules.d/58-lulu-recovery-power.rules
install -D -m 0755 "$root/packaging/mudos-set-initial-password" \
    /usr/libexec/mudos-set-initial-password
install -D -m 0644 "$root/packaging/polkit-1/rules.d/59-lulu-initial-password.rules" \
    /etc/polkit-1/rules.d/59-lulu-initial-password.rules
install -D -m 0644 "$root/packaging/avahi/mudos-http.service" \
    /etc/avahi/services/mudos-http.service

# Avahi is enabled for service discovery, but this provisioner deliberately
# leaves the base resolver and Avahi configuration untouched.  A deployment
# requiring resolver/NSS policy must install a separately owned reversible
# drop-in rather than editing shared system files in place.
systemctl enable --now avahi-daemon.service 2>/dev/null || true
systemctl restart avahi-daemon.service 2>/dev/null || true
systemctl daemon-reload
systemctl reload polkit.service 2>/dev/null || true
systemctl enable lulu-admin.service
systemctl restart lulu-admin.service
systemctl enable --now mudos-recovery.service
echo "provisioned Mudos admin UI on http://mudos.local/"
