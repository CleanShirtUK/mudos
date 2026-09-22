# Acquisition administration surfaces

NZBGet and Transmission Web UIs are standard Mudos appliance administration
surfaces, not development-only features. Normal acquisition provisioning runs
`scripts/provision-appliance-services.sh`, which provisions the admin service,
both native daemons, and LAN-scoped UFW rules. The narrower
`provision-acquisition-services.sh` entrypoint remains available for systems
that do not want to install the admin frontend.

The daemons bind to `0.0.0.0` so loopback provider traffic and trusted-LAN
administration work across DHCP/network startup. Their own authentication and
host/IP protections remain enabled; UPnP and router port forwarding are
disabled. The firewall permits TCP 6789 and 9091 only from the active LAN
subnet/interface. No WAN rule is created.

Default URLs:

- NZBGet: `http://<mudos-host>:6789/`
- Transmission: `http://<mudos-host>:9091/transmission/web/`

Both services use HTTP in the standard configuration. Credentials are
generated/materialized through SecretStore and private daemon state; they are
not recorded here. Mudos providers continue to use `127.0.0.1` RPC endpoints.

Fresh-install/OOBE integration must invoke the same provisioning entrypoint so
reinstall, reboot, and production deployment preserve the standard policy.

The admin UI follows the same appliance-host convention. Avahi advertises
`mudos.local`; if a hostname collision occurs, Avahi applies its normal
collision suffix and the IP address remains available as a fallback.
