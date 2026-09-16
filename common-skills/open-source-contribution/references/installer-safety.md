# Installer And Service Safety

When reviewing install scripts or services, check these bug classes:

- A root service must not execute a binary from a user-writable checkout.
- `ProtectHome=true` breaks services whose `ExecStart` points into `~/...`.
- If side-by-side services are supported, each service needs its own installed
  binary path. Do not make all units point at one shared global binary unless
  that is the documented contract.
- Validate service names, labels, paths, and unit filenames before using them
  in `rm`, `install`, `systemctl`, `launchctl`, or template substitution.
- Reject or safely escape whitespace, `%`, path separators, `..`, and shell
  metacharacters in values that enter service files.
- Uninstall paths need the same validation as install paths.

Prefer service-specific, root-owned install paths for system services, for
example:

```text
/usr/local/lib/<project>/<service-id>/<binary>
```
