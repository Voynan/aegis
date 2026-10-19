# Django adapter — V2 plan

**Status:** planned for after 1.0 ([ADR-0034](../decisions.md#adr-0034-the-django-adapter-moves-to-v2)).
This document is a plan, not a normative part of 1.0.

"V2" names the second product phase. It is not format version 2 — the adapter uses the v1 format
exactly as frozen at M4 — and it need not be SemVer 2.0: the adapter is additive, so it can ship
as a 1.x minor release.

---

## 1. Why it is not in 1.0

The adapter promised a `SealedFileField` that streams uploads into any storage backend,
unseals transparently on read, and fails misconfiguration at `manage.py check`. Turning that
promise into a design surfaced seven problems:

| Q | Problem |
|---|---|
| Q4 | A context callable that reads `inst.pk` cannot work before the first `INSERT`. |
| Q16 | The field had no way to receive its `Vault`. |
| Q38 | Django storage and responses *pull* from file objects; the 1.0 API could only *push*. Solved in the core by the readers ([ADR-0032](../decisions.md#adr-0032-pull-style-readers-vaultsealed-and-vaultunsealed-seekable-when-the-source-is)). |
| Q39 | Under ASGI, Django fully consumes a synchronous response iterator before sending it — `FileResponse` included. Its documentation says this "defeats the purpose" of streaming; Django 5.2 and 6.0 do it with `sync_to_async(list)`. |
| Q41 | The example context, `{"user_id": inst.owner_id}`, is the pattern usage.md calls a trap, and makes all files of one owner interchangeable. |
| Q42 | `upload_to` puts original filenames in storage keys; `FieldFile.url` would point at ciphertext; a decrypting view needs authorization; existing plaintext files need a migration path. |
| — | Every one of these needs tests across Django versions and storage backends, and a security review of its own. |

The core's guarantees do not depend on any of this, and the adapter depends on core APIs —
readers, seekable decryption, `inspect` — that only exist from M3. Building it after 1.0 lets it
dogfood a frozen, reviewed core.

## 2. What Django projects get from 1.0

The core already works from Django, with constant memory, through the public readers:
- **Uploads:** `default_storage.save(name, File(vault.sealed(upload, context=…)))`.
- **WSGI downloads:** `FileResponse(vault.unsealed(storage_file, context=…))`, which takes
  `Content-Length` from the authenticated size when the storage file is seekable.
- **ASGI downloads:** an asynchronous iterator that reads one chunk per `sync_to_async` call.

[usage.md § 10](../usage.md#10-django-and-other-web-frameworks) has the recipes. They are what the
adapter will package, test and harden.

## 3. Decisions already taken

| # | Decision | Resolves |
|---|---|---|
| D1 | **Opaque storage names.** The field names objects `<upload_to>/<uuid4>.aegis`. Original filenames never reach a storage key or object metadata; a model that needs one keeps it in an ordinary field. | Q42 (metadata) |
| D2 | **The default context binds the upload, not the owner:** `{"model": "app_label.Model", "field": "<name>", "file_id": "<the uuid of D1>"}`, merged with an optional developer callable. The uuid exists before the first `INSERT`, so Q4 disappears for the default. A callable that reads `pk` on an unsaved instance raises `UsageError`. Binding each upload also stops substitution between files ([security.md § 3](../security.md#3-what-aegis-does-not-defend-against)). | Q4, Q41 |
| D3 | **The vault comes from a dotted path.** A `vault=` argument on the field overrides an `AEGIS_VAULT` setting; both resolve lazily, so `manage.py migrate` runs on a machine without key material. System checks verify that the vault resolves and does not use `CallerHeld()`. | Q16 |
| D4 | **Uploads stream through `vault.sealed()` into `Storage.save()`.** This works with every backend; memory is bounded by the backend's own buffering. | Q38 |
| D5 | **No public URL to ciphertext.** `FieldFile.url` returns the URL of a decrypting view, and that view requires an authorization callback. There is no default "allow". | Q42 (URL, authorization) |
| D6 | **Serving.** WSGI: `FileResponse` over `vault.unsealed()`. ASGI: an asynchronous iterator, one chunk per thread hop. Range requests are served from the seekable reader when the storage file is seekable. | Q39, Q40 |
| D7 | **Migrating existing plaintext files.** A management command seals them in place, one by one. A transitional read mode, `allow_plaintext=True`, is off by default and logs a warning on every plaintext read. | Q42 (migration) |

## 4. Open questions

| Q | Question |
|---|---|
| V2-Q1 | **Detached custody.** Store the custody record in a model column, so that rotation is a transactional `UPDATE` and works on object stores without rewriting objects. It needs a core API that seals with the record returned instead of written. The file would use the caller-held layout and the record the format of [file-format.md § 2.5](../file-format.md#25-the-custody-record) — additive, with no format change. |
| V2-Q2 | **Range semantics.** Multiple ranges, `If-Range`, caching headers, and what a partial response may reveal about sizes. |
| V2-Q3 | **`ImageField` and thumbnails.** Dimension extraction decrypts the image, and derived images (thumbnails, previews) must be sealed too. |
| V2-Q4 | **Orphaned files.** Django does not delete files with their rows, and sealed orphans are still sensitive. Is a cleanup command in scope? |
| V2-Q5 | **Admin integration.** A widget linking to the decrypting view, and the permission model behind it. |
| V2-Q6 | **Uploads under ASGI.** Large uploads spool to temporary files before the view runs. Seal from there, and make sure the spooled plaintext is deleted. |
| V2-Q7 | **Content type.** Where it is stored (a model field) and how it is served, never derived from a storage name. |

## 5. Milestones

| Milestone | Scope | Definition of done |
|---|---|---|
| D-M1 | The field, the storage wrapper and the system checks (D1–D4) | integration tests on the current Django LTS and the latest release, with `FileSystemStorage` and an S3-compatible backend; a 512 MB upload within the memory invariant |
| D-M2 | The decrypting view, WSGI and ASGI, Range (D5, D6) | a 512 MB download within the memory invariant under both protocols; the authorization path reviewed |
| D-M3 | The migration command and the transitional mode (D7) | a mixed tree of sealed and plaintext files migrates and reads back |
| D-M4 | Detached custody (V2-Q1), if accepted | rotation as a database transaction, tested on an object store |

Every milestone also keeps the dogfood test green: `aegis.contrib.django` imports only the
public API.

## 6. Constraints carried over from the core

- **Public API only.** If the adapter needs a private import, the public API is incomplete, and
  the core gets an addition first.
- **No format change.** Everything above uses format v1.
- **The honest sentence applies unchanged:** Aegis protects data at rest, not a server
  compromised at runtime.
