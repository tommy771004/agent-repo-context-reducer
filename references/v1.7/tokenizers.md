# Tokenizer Providers

The runtime defaults to `native`, a dependency-free UTF-8 bytes/4 estimate.

Optional `tiktoken` is discovered only if already installed. A host can register a process-local tokenizer callback through `register_tokenizer()`.

Security rule: CLI arguments never contain arbitrary Python module/function import paths. Host registration is explicit code-level integration.

An exact token counter does not imply exact API billing because message framing and provider accounting may add overhead outside the supplied text.
