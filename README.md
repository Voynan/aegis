# Aegis

A simple, secure and streaming-friendly file encryption library built on modern cryptography.

## Threat model

Aegis protects files at rest against someone who obtains the storage they live in: a bucket, a
disk, a backup, a database dump. From sealed files they learn sizes, the number of files, and
each file's custody mode and key id. They learn nothing about the content. With write access,
they still cannot alter, reorder or truncate a file without opening it raising an error. A file
bound to one user's context does not open under another's. Aegis draws a fresh data key and a
fresh 256-bit salt for every file, and every file commits to exactly one key, so a ciphertext
crafted to open under two keys is rejected. Aegis does not defend against deleted files, a blob
swapped for another genuine blob sealed under an equal context, or a host already running
attacker code: see [what it does not defend against](https://github.com/Voynan/aegis/blob/main/docs/security.md#3-what-aegis-does-not-defend-against).

## Status

**Pre-1.0. There is no usable API yet.** Version `0.0.0` exists only to reserve the name on
PyPI. The [file format](https://github.com/Voynan/aegis/blob/main/docs/file-format.md) is open for public review before it freezes.
Aegis is [not audited](https://github.com/Voynan/aegis/blob/main/docs/security.md#10-audit-status).

## Install

```bash
pip install aegis-voynan    # imports as `aegis`
```

Nothing is usable before the first real release.

## Documentation

The design documents start at [docs/README.md](https://github.com/Voynan/aegis/blob/main/docs/README.md).

## License

[MIT](https://github.com/Voynan/aegis/blob/main/LICENSE).
