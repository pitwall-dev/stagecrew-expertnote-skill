---
name: stagecrew-expert-note
description: "Create or update StageCrew Expert Notes from Markdown or self-contained HTML through the authenticated REST API; use when the user asks to register, save, publish, or replace an issue report in Expert Note."
version: 1.3.0
author: Pitwall
license: MIT
platforms: [linux, macos]
required_environment_variables: [EXPERT_NOTE_API_URL, EXPERT_NOTE_PAT]
metadata:
  hermes:
    tags: [stagecrew, expert-note, markdown, html, issue-report, rest-api]
---

# StageCrew Expert Note

Use this skill when the user explicitly asks to create/register/save a Markdown or self-contained HTML report in StageCrew Expert Note, or to replace an existing note. Report generation alone must not write a note.

## Prerequisites

Set these in the active Hermes profile's `.env` (never paste values into chat or commit them):

```dotenv
EXPERT_NOTE_API_URL=https://api-dev.pitwall-web.jp/rest/expert-notes
EXPERT_NOTE_PAT=sc_pat_...
```

Create the PAT in StageCrew from **Manage my account → Personal access tokens**. The token is shown once, expires after 90 days, and is scoped to `expertNotes:create`. Store it like a password; never paste it into chat or commit it. Revoke it from the same screen if exposed or no longer needed.

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
- `401`: PAT is absent, malformed, expired, revoked, or does not match its stored hash.
- `403`: the PAT owner is no longer a current member of the organization captured when the token was created.
- `405`: wrong HTTP method.

Do not retry writes automatically after an ambiguous network timeout: the first request may have succeeded. Ask the user to check Expert Note or use the tracing ID before retrying.

## Common pitfalls

1. Do not submit a note merely because a report was generated; require an explicit save/register request.
2. Do not pass multiline Markdown or HTML directly through fragile shell quoting; use `--content-file`.
3. Do not print or commit `EXPERT_NOTE_PAT`.
4. An update replaces all text sections. Read and preserve the intended full body before sending `PUT`.
5. Do not automatically retry an ambiguous write timeout.
6. Use HTTPS for real endpoints. The client rejects non-loopback HTTP and does not follow redirects, preventing the PAT from crossing origins.

## Verification checklist

- [ ] The source passes `--dry-run` validation with the intended content format.
- [ ] The requested operation is explicit: create or update.
- [ ] The HTTP status is exactly `201` for create or `200` for update.
- [ ] The response contains a non-empty Expert Note ID.
- [ ] The returned ID and `logTracingId` are reported without exposing the PAT.
