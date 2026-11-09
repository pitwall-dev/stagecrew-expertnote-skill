# StageCrew Expert Note Skill

A distributable [Hermes Agent](https://github.com/NousResearch/hermes-agent) skill for creating/updating Markdown or HTML Expert Notes and creating native-image Writer notes through the REST API.

## Install

### Direct install

```bash
hermes skills install pitwall-dev/stagecrew-expertnote-skill/skills/stagecrew-expert-note
```

### Add this repository as a skill source

```bash
hermes skills tap add pitwall-dev/stagecrew-expertnote-skill
hermes skills search stagecrew
hermes skills install pitwall-dev/stagecrew-expertnote-skill/skills/stagecrew-expert-note
```

Start a new Hermes session after installation so the skill index reloads.

## Configure

Find the active profile's environment file:

```bash
hermes config env-path
```

Set the endpoint in that file. For standalone text notes, also set a personal access token; never commit the actual PAT.

```dotenv
EXPERT_NOTE_API_URL=https://api-dev.pitwall-web.jp/rest/expert-notes
EXPERT_NOTE_PAT=sc_pat_...
```

Create the PAT in StageCrew under **Manage my account → Personal access tokens**. It must have the `expertNotes:create` scope.

For Writer native-image creation, use a **per-request requester Firebase ID token**, not the PAT. The trusted host can pass it in `EXPERT_NOTE_FIREBASE_BEARER` to the CLI without placing it in a command line or JSON file. If Hermes can read that environment, the trusted host must POST the authored JSON itself instead. Do not persist a Writer bearer in the profile `.env`.

Writer request file example (private, no token):

```json
{"name":"Accepted title","writer":{"sessionId":"session-1","revision":4,"operationId":"commit-1","blocks":[{"type":"text","content":"## Step"},{"type":"image","stepId":"step-1"}]}}
```

```bash
python3 <installed-skill-directory>/scripts/create_expert_note.py --writer-document-file <private-json-path> --dry-run
python3 <installed-skill-directory>/scripts/create_expert_note.py --writer-document-file <private-json-path>
```

The second command requires the trusted per-request bearer environment; it POSTs to `/rest/expert-notes`, expects HTTP 201 plus `data.id`, and never substitutes a Markdown image link for a native image. Preserve the accepted revision, text and step order, and stable operation ID. On an ambiguous write, inspect the Writer session/version before retrying.

## Verify the package and installation

```bash
hermes skills inspect pitwall-dev/stagecrew-expertnote-skill/skills/stagecrew-expert-note
hermes skills list
```

To exercise local input validation without creating a note, resolve the installed
`stagecrew-expert-note` directory shown by Hermes and run:

```bash
python3 <installed-skill-directory>/scripts/create_expert_note.py \
  --name "Installation check" \
  --content "# Installation check" \
  --dry-run
```

To validate self-contained HTML without changing its source, add `--content-format html`:

```bash
python3 <installed-skill-directory>/scripts/create_expert_note.py \
  --name "HTML report" \
  --content-format html \
  --content-file "${TMPDIR:-/tmp}/report.html" \
  --dry-run
```

## Repository layout

```text
skills/stagecrew-expert-note/
├── SKILL.md
└── scripts/
    └── create_expert_note.py
```

## Development

Run the test suite with the Python standard library only:

```bash
python3.11 -m unittest discover -s tests -p 'test_*.py' -v
```

## Security

- Treat `EXPERT_NOTE_PAT` and `EXPERT_NOTE_FIREBASE_BEARER` as passwords.
- Never paste credentials into chat, logs, source files, or issue reports.
- Use HTTPS for non-local endpoints. The client rejects non-loopback HTTP and refuses redirects so the PAT cannot be forwarded to another origin.
- Do not automatically retry an ambiguous write timeout because the first request may have succeeded.

## License

MIT. See [LICENSE](LICENSE).
