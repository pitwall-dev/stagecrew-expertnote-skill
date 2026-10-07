# StageCrew Expert Note Skill

A distributable [Hermes Agent](https://github.com/NousResearch/hermes-agent) skill for creating and updating StageCrew Expert Notes from Markdown or self-contained HTML through the authenticated REST API.

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

Add the following values to that file. Never commit the actual PAT.

```dotenv
EXPERT_NOTE_API_URL=https://api-dev.pitwall-web.jp/rest/expert-notes
EXPERT_NOTE_PAT=sc_pat_...
```

Create the PAT in StageCrew under **Manage my account → Personal access tokens**. It must have the `expertNotes:create` scope.

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
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Security

- Treat `EXPERT_NOTE_PAT` as a password.
- Never paste the PAT into chat, logs, source files, or issue reports.
- Use HTTPS for non-local endpoints. The client rejects non-loopback HTTP and refuses redirects so the PAT cannot be forwarded to another origin.
- Do not automatically retry an ambiguous write timeout because the first request may have succeeded.

## License

MIT. See [LICENSE](LICENSE).
