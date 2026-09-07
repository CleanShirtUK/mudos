# Steam Appliance Ownership

Lulu's Steam integration is owned by the `lulu` appliance account. Steam's
login/session, client state, library roots, manifests, compatibility data, and
game installations must live under the `lulu` account and must be discovered
from that context by `consoled`.

The HOST user's home directory and Steam library are validation-only inputs for
development tests. They are not production runtime sources and must not be
copied, mounted, ACLed, or referenced by the appliance service.

Initial setup is an interactive Steam authentication and library installation
step inside Lulu's graphical session. Credentials must be entered normally by
the operator and must not be stored in the repository, deployment scripts, or
Lulu's catalogue database.

The bounded bootstrap entry point is `scripts/steam-bootstrap.sh`. It is
operator-invoked, runs only as `lulu`, requires the active Lulu Wayland session,
and delegates all authentication and Steam UI interaction to Steam.
