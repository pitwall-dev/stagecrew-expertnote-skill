#!/usr/bin/env python3
"""Create or update one StageCrew Expert Note from Markdown using only the stdlib."""

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Never


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turn redirects into HTTP errors so credentials never cross origins."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def abort(message: str) -> Never:
    raise SystemExit(message)


def validate_api_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        abort("EXPERT_NOTE_API_URL must use HTTPS (HTTP is allowed only for loopback tests)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        abort("EXPERT_NOTE_API_URL must be an absolute URL without credentials or a fragment")
    return url


def read_json(request: urllib.request.Request) -> tuple[int, dict]:
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=30) as response:
            try:
                result = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError):
                abort(
                    f"Invalid JSON response after HTTP {response.status}; "
                    "write status is unknown, do not retry automatically"
                )
            if not isinstance(result, dict):
                abort(
                    f"Invalid JSON response after HTTP {response.status}; "
                    "write status is unknown, do not retry automatically"
                )
            return response.status, result
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body[:500]
        abort(json.dumps({"status": error.code, "error": detail}, ensure_ascii=False))
    except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as error:
        reason = getattr(error, "reason", error)
        abort(f"Network error: {reason}; write status is unknown, do not retry automatically")


def personal_access_token() -> str:
    token = os.getenv("EXPERT_NOTE_PAT", "")
    if not token.startswith("sc_pat_"):
        abort("Set EXPERT_NOTE_PAT to a StageCrew personal access token")
    return token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="update this existing Expert Note instead of creating one")
    parser.add_argument("--name", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--content")
    source.add_argument("--content-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    name = args.name.strip()
    try:
        content = args.content_file.read_text(encoding="utf-8") if args.content_file else args.content
    except OSError as error:
        abort(f"Cannot read content file: {error}")
    if not 1 <= len(name) <= 512:
        abort("name must contain 1-512 characters")
    if not 1 <= len(content) <= 100_000:
        abort("content must contain 1-100000 characters")
    if args.id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args.id):
        abort("id must be a generated Expert Note id")
    payload = {"name": name, "content": content} | ({"id": args.id} if args.id else {})
    if args.dry_run:
        print(json.dumps({
            "valid": True,
            "operation": "update" if args.id else "create",
            "id": args.id,
            "name": name,
            "contentLength": len(content),
        }, ensure_ascii=False))
        return

    url = os.getenv("EXPERT_NOTE_API_URL")
    if not url:
        abort("Set EXPERT_NOTE_API_URL")
    request = urllib.request.Request(
        validate_api_url(url),
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {personal_access_token()}", "Content-Type": "application/json"},
        method="PUT" if args.id else "POST",
    )
    status, result = read_json(request)
    data = result.get("data")
    note_id = data.get("id") if isinstance(data, dict) else None
    expected_status = 200 if args.id else 201
    if status != expected_status or not isinstance(note_id, str) or not note_id.strip():
        abort(json.dumps({"status": status, "error": "response did not contain data.id"}, ensure_ascii=False))
    print(json.dumps({"status": status, "id": note_id, "logTracingId": result.get("logTracingId")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
