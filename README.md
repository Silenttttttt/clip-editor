# video-editor

A browser-based, canvas-timeline non-linear video editor with a real FFmpeg
backend - media bin, timeline with select/razor/delete tools, a Range-request
preview player, an export dialog, project persistence, and undo/redo. Pure
Python **stdlib** (`http.server`), zero pip dependencies - the only external
requirement is `ffmpeg`/`ffprobe` on `PATH`.

Once you export a clip, it can be pushed somewhere else over HTTP through a
small pluggable **upload backend** abstraction:

- **`vps`** (default) - multipart-POSTs the finished video to a server you
  run, e.g. your own upload API.
- **`local-storage`** - pushes to a self-hosted
  [local-storage](https://github.com/Silenttttttt/rust-local-storage-cdn)
  CDN instance instead (a simple, S3-like Rust/axum file store).

## Quick start

```bash
pip install -e .            # optional - or just run the module directly
python3 -m video_editor --upload-backend vps --server https://example.com --api-key KEY
# open http://localhost:7777
```

Or with Docker:

```bash
docker build -t video-editor .
docker run -p 7777:7777 \
  -e UPLOAD_BACKEND=vps -e UPLOAD_SERVER_URL=https://example.com -e UPLOAD_API_KEY=KEY \
  -v video-editor-projects:/data/projects \
  video-editor
```

## Project layout

```
video_editor/
  __main__.py    CLI entry point (python -m video_editor)
  server.py      HTTP handler + routing (upload, process, preview, projects)
  ffmpeg_ops.py  ffprobe/ffmpeg wrappers: media probing + the export pipeline
  projects.py    JSON project persistence + copied-media store
  backends.py    the UploadBackend abstraction + VpsBackend/LocalStorageBackend
  ui.py          the embedded single-page editor UI (HTML/CSS/JS)
  state.py       small in-memory registries shared by the modules above
```

## Configuration

Every setting is a CLI flag or an equivalent env var (flags win if both are set).

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `--upload-backend` | `UPLOAD_BACKEND` | `vps` | `vps` or `local-storage` |
| `--server` | `UPLOAD_SERVER_URL` | - | `vps` backend: base URL of the receiving server |
| `--api-key` | `UPLOAD_API_KEY` | - | `vps` backend: `X-Api-Key` header value |
| `--local-storage-url` | `LOCAL_STORAGE_URL` | - | `local-storage` backend: base URL of the CDN instance |
| `--local-storage-bucket` | `LOCAL_STORAGE_BUCKET` | `video-editor` | `local-storage` backend: bucket to upload into |
| `--local-storage-write-token` | `LOCAL_STORAGE_WRITE_TOKEN` | - | `local-storage` backend: `X-Activator-Write-Token`, only needed if the target instance is write-protected while scaled to zero |
| `--port` | `UPLOAD_PORT` | `7777` | HTTP listen port |
| `--projects-dir` | `PROJECTS_DIR` | `~/.video-editor-projects` | Where project JSON + copied media live - should be a persistent volume in any real deployment |

`--server`/`--api-key` are required (hard error) when `--upload-backend vps`
(the default) - this matches the original script's behavior exactly, so an
existing deployment needs zero changes to keep working. `--local-storage-url`
is required when `--upload-backend local-storage`.

## The two upload backends

### `vps`

Multipart POST to `{server}/api/admin/videos/upload` with header
`X-Api-Key: {api_key}`. Expects a JSON response with a `url` field (a
relative `/...` url gets `server` prefixed onto it automatically). This is
the **exact, unchanged** original behavior.

### `local-storage`

Talks to [local-storage](https://github.com/Silenttttttt/rust-local-storage-cdn)'s
real API:

```
POST /buckets/{bucket}/files
  body: raw file bytes
  Content-Disposition: attachment; filename="X"   <- sets the stored key
  Content-Type: <content type>
```

which returns `201` + a JSON file record on success. The backend builds the
returned `url` from that record's `key` field:
`{base_url}/buckets/{bucket}/files/{key}`.

If the target local-storage instance is deployed scale-to-zero and
write-protected (mutating requests need a shared secret while it's cold),
set `--local-storage-write-token`/`LOCAL_STORAGE_WRITE_TOKEN` to that token.
Reads (playback, listing) never need it.

#### Known, honest limitation

`LocalStorageBackend`'s returned URL is whatever `LOCAL_STORAGE_URL` is
reachable at (e.g. an internal Traefik ingress hostname, or wherever else
that instance is actually exposed) - it is **not** rewritten onto any other
domain. If some other system needs videos processed here to appear under
**its own** public domain, there are exactly two real ways to get there, and
this repo intentionally implements **neither**:

1. Teach that other system's backend to accept a URL reference (fetch the
   bytes itself) instead of requiring a raw upload.
2. Build a reverse-proxy / route-registration layer in front of
   local-storage that publishes it under the target domain.

Anything short of one of those two is not a real integration - don't assume
one exists just because both services happen to live in the same cluster.

## Tests

Stdlib `unittest`, no extra dependencies:

```bash
python3 -m unittest discover -s tests -v
```

`tests/test_ffmpeg_ops.py` covers the ffmpeg command-construction logic
directly (no ffmpeg binary needed - it never shells out). `tests/test_backends.py`
runs both upload backends against a local mock HTTP server, so it exercises
the real request/response handling code without touching any live service or
credential.
