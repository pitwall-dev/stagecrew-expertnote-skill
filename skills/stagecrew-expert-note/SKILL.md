---
name: stagecrew-expert-note
description: "Create StageCrew Expert Notes with text and native images."
version: 1.5.0
author: Pitwall
license: MIT
platforms: [linux, macos]
required_environment_variables: [EXPERT_NOTE_API_URL]
metadata:
  hermes:
    tags: [stagecrew, expert-note, markdown, html, issue-report, rest-api]
---

# StageCrew Expert Note

Use this skill for an explicitly requested Markdown/HTML Expert Note create/update, or for an accepted Writer document with ordered text and native images. Report generation alone must not write a note.

## Prerequisites

Set the API endpoint in the active Hermes profile's `.env`:

```dotenv
EXPERT_NOTE_API_URL=https://api-dev.pitwall-web.jp/rest/expert-notes
```

For standalone Markdown/HTML notes only, configure `EXPERT_NOTE_PAT=sc_pat_...` in that profile's `.env`. Create it in StageCrew from **Manage my account → Personal access tokens** with `expertNotes:create` scope. It expires after 90 days. Never use this shared PAT for Cloud Run Writer.

For Writer, the trusted request owner must supply their current Firebase ID token to the REST request. The CLI accepts it only from `EXPERT_NOTE_FIREBASE_BEARER` in its process environment, not from arguments or the JSON document. The Cloud Run integration must inject it per request in a trusted layer; if the model can inspect that environment or tool arguments, use a server-side REST tool instead of exposing the bearer to Hermes. Do not store the token in a shared profile `.env`, log, file, or chat.

## Create workflow

1. Preserve the requested source format. Markdown is the default; use `--content-format html` for self-contained HTML. Do not convert between formats.
2. Pick a concise note title (1–512 characters); content must be 1–100,000 characters.
3. Write the source to a temporary file in the platform's temporary directory so shell quoting cannot damage formatting. The examples below use `${TMPDIR:-/tmp}` in a Bash-compatible shell.
4. Resolve `scripts/create_expert_note.py` relative to this skill directory.
5. Validate locally first:

```bash
python3 scripts/create_expert_note.py --name "<title>" --content-file "${TMPDIR:-/tmp}/report.md" --dry-run
```

6. Only after an explicit create/register/save request, submit it:

```bash
python3 scripts/create_expert_note.py --name "<title>" --content-file "${TMPDIR:-/tmp}/report.md"
```

7. Report the returned Expert Note ID and `logTracingId`. Never claim create success unless the API returned HTTP 201; never claim update success unless it returned HTTP 200. Both require a non-empty ID.
8. Delete the temporary report file if it contains sensitive incident details.

For HTML, use the same workflow with an `.html` file:

```bash
python3 scripts/create_expert_note.py --name "<title>" --content-format html --content-file "${TMPDIR:-/tmp}/report.html" --dry-run
python3 scripts/create_expert_note.py --name "<title>" --content-format html --content-file "${TMPDIR:-/tmp}/report.html"
```

HTML is stored unchanged and rendered inside the Expert Note sandbox. Viewing it requires the organization's HTML-document feature to be enabled.

## Native-image video Writer workflow

After the requester accepts the Writer preview, Hermes authors the Expert Note title, text, and image-block selection/order from that session. The accepted preview is source context, not a byte-exact editorial constraint: Hermes may improve wording and presentation. Reference only approved image step IDs; do not invent image paths, owner, or output IDs. Images are `{ "type": "image", "stepId": "<approved-step-id>" }`, not Markdown links or HTML embeds. Text is `{ "type": "text", "content": "..." }` (Markdown), or adds `"contentFormat": "html"` for safe HTML. The server verifies current requester membership, the accepted revision and image assets, then copies images and creates the private Expert Note/version. Never use the PAT for this flow.

The trusted Writer integration supplies `sessionId`, current accepted `revision`, and one stable `operationId` for this commit. Place only the API body in a private JSON file, preserving block order:

```json
{"name":"Accepted title","writer":{"sessionId":"session-1","revision":4,"operationId":"commit-1","blocks":[{"type":"text","content":"## First step"},{"type":"image","stepId":"step-1"},{"type":"text","content":"Next step"}]}}
```

Validate with `terminal(command="python3 scripts/create_expert_note.py --writer-document-file <private-json-path> --dry-run")`. The trusted layer can submit using `terminal(command="python3 scripts/create_expert_note.py --writer-document-file <private-json-path>")` **only if** the per-request bearer is injected into that process without granting the model read access to it. Otherwise have the trusted server-side tool POST the same JSON to `/rest/expert-notes` with the requester's Firebase ID token in the Authorization header, attached entirely outside the model's access. Do not put a token in a shell command, model tool argument, or document file. Remove the private document after use.

POST returns HTTP 201 with a non-empty `data.id` on success. If the response is ambiguous, read back that Writer session/version and operation before reporting success or considering a retry with the **same** operation ID; never automatically rerun paid work.

## Update workflow

Updating replaces the note title and all text sections with the supplied Markdown or HTML while preserving existing media and their relative order. Obtain the exact Expert Note ID, validate locally, then submit only after an explicit update request:

```bash
python3 scripts/create_expert_note.py --id "<expert-note-id>" --name "<title>" --content-file "${TMPDIR:-/tmp}/report.md" --dry-run
python3 scripts/create_expert_note.py --id "<expert-note-id>" --name "<title>" --content-file "${TMPDIR:-/tmp}/report.md"
```

For HTML, add `--content-format html` and use the complete `.html` source file.

The API writes an edit-history entry and rejects missing notes or notes outside the PAT organization with `404`.

## Failure interpretation

- `404`: Dev LB route has not been applied/reached; do not treat it as an authentication failure.
- `401`: missing/invalid Firebase bearer or invalid/expired/revoked PAT (legacy).
- `403`: requester is not a current member or Writer session/image permission was denied.
- `409`: stale accepted revision or conflicting Writer operation; inspect the session before retrying.
- `405`: wrong HTTP method.

Do not retry writes automatically after an ambiguous network timeout: the first request may have succeeded. Ask the user to check Expert Note or use the tracing ID before retrying.

## Common pitfalls

1. Do not submit a note merely because a report was generated; require an explicit save/register request.
2. Do not pass multiline Markdown or HTML directly through fragile shell quoting; use `--content-file`.
3. Do not print or commit the PAT or per-request Firebase bearer.
4. An update replaces all text sections. Read and preserve the intended full body before sending `PUT`.
5. Do not automatically retry an ambiguous write timeout.
6. Use HTTPS for real endpoints. The client rejects non-loopback HTTP and does not follow redirects, preventing credentials from crossing origins.

## Verification checklist

- [ ] The source passes `--dry-run` validation with the intended content format.
- [ ] For Writer, the JSON preserves accepted session/revision and block order; auth comes from that requester's Firebase bearer, not a PAT.
- [ ] The requested operation is explicit: create or update.
- [ ] The HTTP status is exactly `201` for create or `200` for update.
- [ ] The response contains a non-empty Expert Note ID.
- [ ] The returned ID and `logTracingId` are reported without exposing the PAT.
