#!/usr/bin/env python3
"""Create or update text notes, or POST a native-image Writer note, using only stdlib."""

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


def read_json(request: urllib.request.Request, secret: str = "") -> tuple[int, dict]:
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
        message = json.dumps({"status": error.code, "error": detail}, ensure_ascii=False)
        abort(message.replace(secret, "[REDACTED]") if secret else message)
    except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as error:
        reason = getattr(error, "reason", error)
        message = f"Network error: {reason}; write status is unknown, do not retry automatically"
        abort(message.replace(secret, "[REDACTED]") if secret else message)


def personal_access_token() -> str:
    token = os.getenv("EXPERT_NOTE_PAT", "")
    if not token.startswith("sc_pat_"):
        abort("Set EXPERT_NOTE_PAT to a StageCrew personal access token")
    return token

def writer_document(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as stream:
            body = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        abort("Cannot read valid Writer JSON file")
    identifier = lambda value: isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
    if not isinstance(body, dict) or set(body) != {"name", "writer"} or not isinstance(body["name"], str) or not 1 <= len(body["name"]) <= 512 or not body["name"].strip():
        abort("Invalid Writer document")
    writer = body["writer"]
    if not isinstance(writer, dict) or set(writer) != {"sessionId", "revision", "operationId", "blocks"} or not identifier(writer["sessionId"]) or not identifier(writer["operationId"]) or type(writer["revision"]) is not int or writer["revision"] < 0 or not isinstance(writer["blocks"], list) or not 1 <= len(writer["blocks"]) <= 100:
        abort("Invalid Writer document")
    text_size = 0
    for block in writer["blocks"]:
        if not isinstance(block, dict):
            abort("Invalid Writer block")
        if block.get("type") == "image":
            if set(block) != {"type", "stepId"} or not identifier(block["stepId"]):
                abort("Invalid Writer image block")
        elif block.get("type") == "text":
            if set(block) not in ({"type", "content"}, {"type", "content", "contentFormat"}) or not isinstance(block["content"], str) or not 1 <= len(block["content"]) <= 100_000 or ("contentFormat" in block and block["contentFormat"] != "html"):
                abort("Invalid Writer text block")
            text_size += len(block["content"])
        else:
            abort("Invalid Writer block type")
    if text_size > 100_000:
        abort("Writer document exceeds text limits")
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="update this existing Expert Note instead of creating one")
    parser.add_argument("--name")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--content")
    source.add_argument("--content-file", type=Path)
    source.add_argument("--writer-document-file", type=Path)
    parser.add_argument("--content-format", choices=("markdown", "html"), default="markdown")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.writer_document_file:
        if args.id or args.name or args.content_format != "markdown":
            parser.error("Writer document cannot be combined with legacy note options")
        payload = writer_document(args.writer_document_file)
        if args.dry_run:
            print(json.dumps({"valid": True, "operation": "writer-create", "blockCount": len(payload["writer"]["blocks"])}))
            return
        url = os.getenv("EXPERT_NOTE_API_URL")
        if not url:
            abort("Set EXPERT_NOTE_API_URL")
        bearer = os.getenv("EXPERT_NOTE_FIREBASE_BEARER", "")
        if not bearer or bearer.startswith("sc_pat_") or "\n" in bearer or "\r" in bearer:
            abort("Set EXPERT_NOTE_FIREBASE_BEARER to a per-request Firebase ID token (not a PAT)")
        request = urllib.request.Request(validate_api_url(url), data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}, method="POST")
        status, result = read_json(request, bearer)
        if bearer in json.dumps(result):
            abort("Response contained a credential; write status is unknown, do not retry automatically")
        data = result.get("data")
        note_id = data.get("id") if isinstance(data, dict) else None
        if status != 201 or not isinstance(note_id, str) or not note_id.strip():
            abort(json.dumps({"status": status, "error": "response did not contain data.id"}))
        print(json.dumps({"status": status, "id": note_id, "logTracingId": result.get("logTracingId")}, ensure_ascii=False))
        return

    if args.name is None:
        parser.error("--name is required for text notes")

    name = args.name.strip()
    try:
        if args.content_file:
            with args.content_file.open("r", encoding="utf-8", newline="") as content_stream:
                content = content_stream.read()
        else:
            content = args.content
    except OSError as error:
        abort(f"Cannot read content file: {error}")
    if not 1 <= len(name) <= 512:
        abort("name must contain 1-512 characters")
    if not 1 <= len(content) <= 100_000:
        abort("content must contain 1-100000 characters")
    if args.id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args.id):
        abort("id must be a generated Expert Note id")
    payload = (
        {"name": name, "content": content}
        | ({"contentFormat": "html"} if args.content_format == "html" else {})
        | ({"id": args.id} if args.id else {})
    )
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
