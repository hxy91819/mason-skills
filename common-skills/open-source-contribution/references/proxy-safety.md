# Proxy And Streaming Safety

For HTTP proxy projects used by interactive agents:

- Do not log prompts, response bodies, authorization headers, or tokens.
- Copy hop-by-hop headers carefully.
- Preserve streaming semantics. If using `net/http` directly, flush writable
  chunks when `http.Flusher` is available.
- Add focused tests for request mutation and streaming/flush behavior.
- Keep default bind address on `127.0.0.1` unless remote access is explicit and
  secured.
