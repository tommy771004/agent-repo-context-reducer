# Container sandbox adapter

The container adapter is an optional execution boundary over Podman/Docker. It never makes container execution implicit.

Defaults:

- `network=none`
- `pull=never`
- `repo_mode=ro`
- container root read-only
- `cap-drop=ALL`
- `no-new-privileges`
- non-root user
- PID, memory and CPU limits
- bounded `/tmp` tmpfs
- JSON stdin/stdout contract

`--allow-external-commands` authorizes starting the container engine. It does **not** authorize container network or repository writes. Those require `--allow-runtime-network` and `--allow-runtime-write` respectively.

Image pull uses the engine/host network before the container starts, therefore non-`never` pull policy also requires runtime-network authorization.

Containers reduce host exposure but are not equivalent to a VM or hardware security boundary.
