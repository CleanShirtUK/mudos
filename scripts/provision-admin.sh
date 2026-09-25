#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) -ne 0 ]]; then exec sudo -n "$0" "$@"; fi
root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
service_root=${LULU_SERVICE_ROOT:-$root}
sed "s#/opt/lulu/current#$service_root#g" "$root/packaging/lulu-admin.service" > /etc/systemd/system/lulu-admin.service
install -D -m 0755 "$root/packaging/mudos-provider-install" "$service_root/bin/mudos-provider-install"
sed "s#/opt/lulu/current#$service_root#g" "$root/packaging/lulu-provider-install@.service" \
    > /etc/systemd/system/lulu-provider-install@.service
install -D -m 0644 "$root/packaging/polkit-1/rules.d/57-lulu-provider-install.rules" \
    /etc/polkit-1/rules.d/57-lulu-provider-install.rules
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

# Avahi owns the appliance's mDNS/DNS-SD socket.  systemd-resolved may still
# provide ordinary DNS, but its independent mDNS listener conflicts with
# Avahi on UDP 5353 and makes .local resolution unreliable.
mkdir -p /etc/systemd/resolved.conf.d
cat > /etc/systemd/resolved.conf.d/50-lulu-avahi.conf <<'EOF'
[Resolve]
MulticastDNS=no
EOF
if grep -q '^hosts:' /etc/nsswitch.conf && ! grep -q '^hosts:.*mdns_minimal' /etc/nsswitch.conf; then
    sed -i 's/^hosts: /hosts: mdns_minimal [NOTFOUND=return] /' /etc/nsswitch.conf
fi
systemctl restart systemd-resolved.service
if [[ -f /etc/avahi/avahi-daemon.conf ]]; then
    if grep -q '^#\?host-name=' /etc/avahi/avahi-daemon.conf; then
        sed -i 's/^#\?host-name=.*/host-name=mudos/' /etc/avahi/avahi-daemon.conf
    else
        printf '\nhost-name=mudos\n' >> /etc/avahi/avahi-daemon.conf
    fi
fi
systemctl enable --now avahi-daemon.service 2>/dev/null || true
systemctl restart avahi-daemon.service 2>/dev/null || true
systemctl daemon-reload
systemctl reload polkit.service 2>/dev/null || true
systemctl enable lulu-admin.service
systemctl restart lulu-admin.service
systemctl enable --now mudos-recovery.service
echo "provisioned Mudos admin UI on http://mudos.local/"
