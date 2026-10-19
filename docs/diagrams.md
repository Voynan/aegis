# How Aegis works, in diagrams

Pictures of what the other documents specify, for a reader who wants the mechanism before the
details. **Not normative:** where a diagram and a document disagree, the document wins —
[file-format.md](file-format.md) for bytes, [architecture.md](architecture.md) for code,
[security.md](security.md) for claims.

The diagrams are [Mermaid](https://mermaid.js.org). GitHub renders them in place; in VS Code,
use a Mermaid-capable Markdown preview. Colours mean the same thing in every figure:

| Colour | Means |
|---|---|
| amber | secret material — never stored in the clear |
| blue | stored at rest — safe to leak |
| red | where the cryptographic risk lives, or an error being raised |

---

## 1. The big picture

**Plaintext and keys meet only inside your process; what reaches storage is self-contained
ciphertext, and the master key is never stored next to it.**

```mermaid
flowchart LR
    subgraph proc["Your application process"]
        app["Your code<br/>Django · FastAPI · a job · the CLI"]
        vault["aegis.Vault"]
    end

    subgraph custody["Master key — chosen once, in the constructor"]
        localkek["Local KEK<br/>EnvKey · FileKey · BytesKey"]
        kms["Your KMS or HSM<br/>any KeySource"]
        enduser["The end user<br/>CallerHeld"]
    end

    subgraph rest["At rest — what a leak exposes"]
        store[("Disk or object store<br/>.aegis files")]
        db[("Your database<br/>context fields")]
    end

    app -- "plaintext + context" --> vault
    localkek -- "loaded once, at startup" --> vault
    vault -- "sends each DEK to wrap and unwrap" --> kms
    vault -. "hands back the DEK in the Receipt" .-> enduser
    vault -- "writes header + encrypted chunks" --> store
    app -- "keeps document_id, revision" --> db

    classDef secret fill:#fff8c5,stroke:#9a6700,color:#1f2328
    classDef atrest fill:#ddf4ff,stroke:#0969da,color:#1f2328
    class localkek,kms,enduser secret
    class store,db atrest
```

- **What a leak shows.** Someone who steals the bucket and the database learns file sizes, file
  count, and which key id sealed each file — nothing about content. The context fields in your
  database are not secret: they bind, they do not encrypt.
- **Where the key ends up.** With a local KEK, the key sits in process memory. With a KMS, only
  per-file data keys ever do. With `CallerHeld`, Aegis keeps nothing.
- **What Aegis cannot fix.** A server compromised at runtime sees what the process sees, which is
  why Aegis does not claim to stop it
  ([security.md § 3](security.md#3-what-aegis-does-not-defend-against)).

## 2. Inside the package

**Every import points downward, the cryptographic risk sits in two small pure modules, and
randomness enters in exactly one place.**

```mermaid
flowchart TB
    cli["aegis.cli<br/>adapter — public API only"]
    api["aegis/__init__.py<br/>the public API"]

    subgraph orchestration["Orchestration"]
        vault["vault.py<br/>draws the DEK and the salt"]
        rotate["rotate.py<br/>in-place rotation · rewrap"]
    end

    subgraph ioshape["I/O shape and configuration"]
        readers["readers.py<br/>pull and seekable readers"]
        info["info.py<br/>inspect — never decrypts"]
        keys["keys.py<br/>key sources"]
        ctx["context.py<br/>canonical context"]
    end

    subgraph cryptofmt["Crypto and format — pure"]
        stream["stream.py<br/>chunks · nonces · truncation"]
        envelope["envelope.py<br/>key schedule · commitment<br/>DEK wrap"]
        fmt["format.py<br/>header bytes ↔ records"]
    end

    lib[("cryptography<br/>OpenSSL")]

    cli --> api
    api --> vault & rotate
    vault --> readers & info & keys & ctx
    rotate --> keys
    readers --> stream
    keys --> envelope
    info & ctx --> fmt
    stream -- "AES-256-GCM" --> lib
    envelope -- "HKDF · AES-256-GCM" --> lib

    classDef risk fill:#ffebe9,stroke:#cf222e,color:#1f2328
    class stream,envelope risk
```

- **Reading the arrows.** Every arrow reads "imports", and every one points down; nothing
  points up or sideways, and a test enforces it.
- **What is left out.** Only the main paths are drawn. `vault.py` and `rotate.py` also import the
  bottom layer directly, and `errors.py` — the leaf every module imports — is omitted.
- **Where randomness and the environment enter.** Only `vault.py` calls `os.urandom` — two calls
  per seal — and only `keys.py` reads the environment and key files.
- **Why the vectors need no mocks.** The two red modules receive every key, salt and nonce as a
  parameter, so the frozen vectors can pin their output without patching anything
  ([architecture.md § 4](architecture.md#4-the-purity-boundary-randomness-lives-at-the-edges)).

## 3. From one master key to every chunk

**One master key protects any number of files, but every file gets its own data key and salt —
and therefore its own body key, nonce prefix and key commitment.**

```mermaid
flowchart TB
    kek["KEK — 32 B<br/>yours, or inside your KMS"]
    dek["DEK — 32 B<br/>random per file<br/>drawn by Aegis"]
    salt["salt — 32 B<br/>random per file<br/>stored in the header"]

    wrapkey["wrapping key<br/>HKDF-SHA256 of KEK and salt"]
    wrapped["wrapped DEK<br/>in the custody record"]
    schedule{{"HKDF-SHA256"}}

    bodykey["body key — 32 B"]
    prefix["nonce prefix — 7 B"]
    commit["commitment — 32 B<br/>in the header"]
    chunks["every chunk<br/>AES-256-GCM"]

    kek -- "ikm" --> wrapkey
    wrapkey -- "encrypts" --> wrapped
    dek -- "is wrapped into" --> wrapped
    dek -- "ikm" --> schedule
    salt -- "salt" --> schedule
    schedule --> bodykey & prefix & commit
    bodykey -- "encrypts" --> chunks
    prefix -- "nonce = prefix ‖ counter ‖ last flag" --> chunks
    commit -. "checked before any chunk is decrypted" .-> chunks

    classDef secret fill:#fff8c5,stroke:#9a6700,color:#1f2328
    classDef atrest fill:#ddf4ff,stroke:#0969da,color:#1f2328
    class kek,dek,wrapkey,bodykey,prefix secret
    class salt,wrapped,commit atrest
```

- **The custody modes change only the left branch.** It is drawn for a local KEK. A KMS performs
  its own wrap there instead; with `CallerHeld` there is no wrap, and the user keeps the DEK.
- **Rotation changes only the wrapped DEK.** The DEK, the salt, and everything derived from them
  stay as they are, which is why file bodies are never touched.
- **What the commitment buys.** A header opens under exactly one DEK, and a wrong key fails
  before the body: `KeyMismatch`, not a vague error
  ([file-format.md § 3](file-format.md#3-key-hierarchy)).

## 4. A sealed file

**Everything rotation must change sits in one rewritable record; everything else is fixed at
sealing time and authenticated by every chunk.**

```mermaid
flowchart LR
    subgraph header["Header"]
        core["Core — 73 B, immutable<br/>magic · version · suite<br/>custody · salt<br/>commitment · custody_len"]
        record["Custody record<br/>custody_len B, rewritable<br/>key_id · payload_len<br/>wrapped DEK · padding"]
    end

    subgraph body["Body — N ≥ 1 chunks"]
        c0["chunk 0<br/>65 552 B"]
        c1["chunk 1<br/>65 552 B"]
        cdots["…"]
        clast["final chunk<br/>16 – 65 552 B"]
    end

    rotation(["rotation"])

    core --- record --- c0 --- c1 --- cdots --- clast
    core -. "in the AAD of every chunk" .-> body
    rotation -- "rewrites only" --> record

    classDef atrest fill:#ddf4ff,stroke:#0969da,color:#1f2328
    class core,record,c0,c1,clast atrest
```

- **Size.** The custody record is 66 bytes for a local KEK, absent for caller-held files, and up
  to 4 096 bytes for a KMS wrap. Each chunk adds 16 bytes of tag to its 64 KiB of plaintext.
- **What the nonce detects.** Every chunk's nonce carries its position and a final-chunk flag, so
  reordering, dropping or appending chunks fails to authenticate, and so does a body that ends
  early ([file-format.md § 4](file-format.md#4-chunks)).

## 5. Sealing, step by step

**The context is checked before any I/O, the header is written before any plaintext is read,
and then the body streams through one segment at a time.**

```mermaid
sequenceDiagram
    autonumber
    participant App as Your code
    participant V as vault.py
    participant C as context.py
    participant E as envelope.py
    participant K as Your KMS
    participant S as stream.py
    participant D as Destination

    App->>V: seal(src, dst, context)
    V->>C: canonicalize(context)
    C-->>V: canonical bytes, or UsageError before any I/O
    Note over V: draw DEK and salt — os.urandom, 32 B each
    V->>E: schedule(DEK, salt)
    E-->>V: body key, nonce prefix, commitment
    alt local KEK
        V->>E: wrap the DEK under HKDF(KEK, salt)
    else external custody
        V->>K: wrap(DEK, custody AAD)
    else caller-held
        Note over V: no custody record — the DEK goes back in the Receipt
    end
    V->>D: header core + custody record
    loop each 64 KiB segment, read one ahead
        V->>S: encrypt(segment, counter, last?)
        S->>D: ciphertext + 16-byte tag
    end
    V-->>App: Receipt(size, key_id, key if caller-held)
```

- **Memory.** Exactly one segment is in flight at any time, which is what keeps memory constant
  for a file of any size.
- **Reading ahead.** The writer must know whether a segment is the last before encrypting it, so
  it reads one segment ahead, and it never rewinds: the destination may be a pipe or a socket.
- **The pull form.** `vault.sealed(src)` performs the same steps lazily, as the reader is read
  ([file-format.md § 6.1](file-format.md#61-sealing)).

## 6. Unsealing: every check, in order

**Each failure is reported by the first check that can prove it: argument errors before a byte
is read, key errors before a chunk is decrypted, and truncation only where it is provable.**

```mermaid
flowchart TD
    start(["unseal · unsealed · unseal_bytes · unseal_to_path"])

    subgraph before["Before a byte is read"]
        args{"context and<br/>arguments valid?"}
    end

    subgraph fromheader["From the header, before any chunk"]
        magic{"magic<br/>matches?"}
        vers{"version and<br/>suite known?"}
        wellformed{"header<br/>well formed?"}
        mode{"custody mode<br/>fits the vault?"}
        kid{"key_id<br/>configured?"}
        keyok{"unwrap and<br/>commitment OK?"}
    end

    subgraph inbody["The body, chunk by chunk"]
        chunkok{"chunk authentic<br/>and canonical?"}
        more{"more<br/>chunks?"}
        cut{"cut<br/>provable?"}
    end

    UE["UsageError"]
    NAF["NotAnAegisFile"]
    UV["UnsupportedVersion"]
    MH["MalformedHeader"]
    UK["UnknownKek"]
    KM["KeyMismatch"]
    TF["TruncatedFile"]
    UF["UnsealFailed<br/>wrong context, or damaged data"]
    ok(["complete, authentic plaintext"])

    start --> args
    args -- no --> UE
    args -- yes --> magic
    magic -- no --> NAF
    magic -- yes --> vers
    vers -- no --> UV
    vers -- yes --> wellformed
    wellformed -- no --> MH
    wellformed -- yes --> mode
    mode -- "caller-held vs server custody" --> UE
    mode -- "local KEK vs KMS" --> UK
    mode -- yes --> kid
    kid -- no --> UK
    kid -- yes --> keyok
    keyok -- no --> KM
    keyok -- yes --> chunkok
    chunkok -- yes --> more
    more -- yes --> chunkok
    more -- no --> ok
    chunkok -- no --> cut
    cut -- "yes: no chunk, 1–15 B,<br/>or at a chunk boundary" --> TF
    cut -- "no: inside a chunk" --> UF

    classDef err fill:#ffebe9,stroke:#cf222e,color:#1f2328
    class UE,NAF,UV,MH,UK,KM,TF,UF err
```

- **What `UnsealFailed` still means.** By the time the body is read, the key has passed the
  commitment check. So `UnsealFailed` means a wrong context or damaged data — never a wrong key.
- **The order of checks.** It is what makes errors actionable: `UnknownKek` means "you are missing
  a key", not "your file is broken".
- **Seekable readers.** `unsealed()` over a seekable source runs the truncation check at open,
  on the final chunk, before returning any byte
  ([file-format.md § 6.2](file-format.md#62-unsealing)).

## 7. Reading at an offset

**A seekable reader authenticates the final chunk before it returns anything, so it knows the
exact size and that nothing was cut; afterwards it decrypts only the chunks a read covers.**

```mermaid
sequenceDiagram
    participant App as Your code
    participant R as UnsealedReader
    participant Src as Seekable source

    App->>R: vault.unsealed(src, context)
    R->>Src: read the header
    Note over R: recover the DEK, check the commitment
    R->>Src: seek to the final chunk and read it
    Note over R: authenticate it as final — the plaintext size is now proven
    R-->>App: reader, with reader.size set
    App->>R: seek(offset), then read(n)
    R->>Src: read only the chunks covering offset to offset + n
    Note over R: each chunk is authenticated at its own index
    R-->>App: authentic plaintext
```

- **Where this matters.** HTTP Range requests, media players and libraries that seek (`zipfile`,
  Pillow, PDF readers) work without decrypting the whole file.
- **Opening costs one chunk.** One extra chunk decryption buys the guarantee that a truncated file
  never yields a single byte.
- **A non-seekable source** — a socket, an S3 body — gets a forward-only reader instead, with the
  streaming trust boundary of [security.md § 6](security.md#6-the-streaming-trust-boundary).

## 8. Rotating a key

**Rotation rewrites one small record per file and never reads the body; a journal makes a power
cut mid-write recoverable.**

```mermaid
flowchart TD
    start(["vault.rotate(path)"])
    leftover{"journal left<br/>by a crash?"}
    recover["recover first:<br/>keep the record that opens"]
    check["recover the DEK<br/>check the commitment"]
    untouched["file left untouched"]
    current{"already under<br/>the primary key?"}
    noop(["no-op —<br/>nothing written"])
    step1["1 · journal the old record<br/>fsync it and its directory"]
    step2["2 · write the new record<br/>at offset 73 · fsync"]
    step3["3 · delete the journal"]
    rotated(["rotated —<br/>core and body unchanged"])

    start --> leftover
    leftover -- yes --> recover --> check
    leftover -- no --> check
    check -- "UnknownKek or KeyMismatch" --> untouched
    check -- ok --> current
    current -- yes --> noop
    current -- no --> step1 --> step2 --> step3 --> rotated
```

- **Cost.** It is a few `fsync`s per file, so it scales with the number of files, never with their
  size.
- **Object stores.** S3, GCS and Azure Blob cannot rewrite part of an object, so there
  `vault.rewrap(src, dst)` streams a new copy instead: a new header, and the body bytes copied
  verbatim, never decrypted.
- **What rotation does not undo.** Copies made before rotation — backups, object versions — still
  open with the old key ([security.md § 5.2](security.md#52-what-rotation-does-and-does-not-do)).
