# Installer, service, and proxy review

Read the section matching the changed code.

## Installer And Service Safety

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

## Proxy And Streaming Safety

For HTTP proxy projects used by interactive agents:

- Do not log prompts, response bodies, authorization headers, or tokens.
- Copy hop-by-hop headers carefully.
- Preserve streaming semantics. If using `net/http` directly, flush writable
  chunks when `http.Flusher` is available.
- Add focused tests for request mutation and streaming/flush behavior.
- Keep default bind address on `127.0.0.1` unless remote access is explicit and
  secured.
