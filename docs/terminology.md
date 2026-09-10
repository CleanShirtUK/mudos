# Terminology

Use these scopes when writing new documentation. Existing dated records may
retain historical names where that is important to the evidence.

| Term | Meaning | Examples |
| --- | --- | --- |
| Mudos | The software platform, console UI, services, contracts, and user-facing product concepts | Home, Library, Settings, Guide, catalogue |
| Lulu | The BC-250 machine/appliance and its dressed-up deployment | `lulu` account, `/var/lib/lulu`, systemd units, target hardware |
| development host | The machine and user session used to develop or collect evidence | host OS identity, host display, host Steam library |
| appliance runtime | The installed Lulu deployment running Mudos under the `lulu` account | production service paths and session startup |
| host platform | Operating-system or machine information, not an emulation platform | kernel, hostname, OS/platform string |
| emulation platform | A configured console/content family | `nes`, `genesis`, `ps2`, `wii`, `switch` |

## Rules

- Use Mudos for software-platform behavior and UI navigation.
- Use Lulu for BC-250-specific hardware, account, paths, packaging, deployment,
  or machine validation.
- Keep literal service names, environment variables, filesystem paths, and
  profile identifiers unchanged unless the implementation changes.
- Qualify evidence as development-host, appliance-runtime, or BC-250 evidence.
- When scope cannot be established, retain the existing wording and add it to
  the ambiguity list in the reconciliation backlog.
