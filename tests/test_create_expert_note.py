#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "stagecrew-expert-note"
    / "scripts"
    / "create_expert_note.py"
)
SPEC = importlib.util.spec_from_file_location("create_expert_note", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecordingHandler(BaseHTTPRequestHandler):
    seen = []
    response_status = 201
    response_body = {"data": {"id": "note-123"}, "logTracingId": "trace-456"}
    redirect_url: str = ""

    def log_message(self, format, *args):
        pass

    def handle_request(self):
        size = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(size)
        type(self).seen.append({
            "authorization": self.headers.get("Authorization"),
            "body": json.loads(raw) if raw else None,
            "method": self.command,
        })
        if type(self).redirect_url:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_url)
            self.end_headers()
            return
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(type(self).response_body).encode())

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request


def start_server(**attributes):
    handler = type("ConfiguredHandler", (RecordingHandler,), {"seen": [], **attributes})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, handler


def stop_server(server):
    server.shutdown()
    server.server_close()


class CreateExpertNoteTest(unittest.TestCase):
    def run_cli(self, *args, url=None):
        env = os.environ | {
            "EXPERT_NOTE_API_URL": url or "http://127.0.0.1:1/rest/expert-notes",
            "EXPERT_NOTE_PAT": "sc_pat_test_secret",
        }
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            env=env,
            text=True,
            capture_output=True,
        )

    def test_uses_pat_and_preserves_markdown(self):
        server, handler = start_server()
        try:
            run = self.run_cli(
                "--name", " Incident ",
                "--content", "# Report\n\n|A|B|\n|-|-|",
                url=f"http://127.0.0.1:{server.server_port}/rest/expert-notes",
            )
        finally:
            stop_server(server)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {"status": 201, "id": "note-123", "logTracingId": "trace-456"})
        self.assertEqual(handler.seen, [{
            "authorization": "Bearer sc_pat_test_secret",
            "method": "POST",
            "body": {"name": "Incident", "content": "# Report\n\n|A|B|\n|-|-|"},
        }])

    def test_updates_by_id_with_put(self):
        server, handler = start_server(
            response_status=200,
            response_body={"data": {"id": "note-123"}, "logTracingId": "trace-456"},
        )
        try:
            run = self.run_cli(
                "--id", "note-123", "--name", "Updated", "--content", "New report",
                url=f"http://127.0.0.1:{server.server_port}/rest/expert-notes",
            )
        finally:
            stop_server(server)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {"status": 200, "id": "note-123", "logTracingId": "trace-456"})
        self.assertEqual(handler.seen[0]["method"], "PUT")
        self.assertEqual(handler.seen[0]["body"], {"id": "note-123", "name": "Updated", "content": "New report"})

    def test_redirect_is_rejected_and_pat_does_not_reach_destination(self):
        destination, destination_handler = start_server()
        redirect_url = f"http://127.0.0.1:{destination.server_port}/redirected"
        source, source_handler = start_server(redirect_url=redirect_url)
        try:
            run = self.run_cli(
                "--name", "Redirect", "--content", "Report",
                url=f"http://127.0.0.1:{source.server_port}/rest/expert-notes",
            )
        finally:
            stop_server(source)
            stop_server(destination)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('"status": 302', run.stderr)
        self.assertEqual(len(source_handler.seen), 1)
        self.assertEqual(destination_handler.seen, [])

    def test_non_loopback_http_url_is_rejected_before_request(self):
        run = self.run_cli(
            "--name", "Unsafe URL", "--content", "Report",
            url="http://example.com/rest/expert-notes",
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("must use HTTPS", run.stderr)

    def test_ambiguous_transport_failures_warn_not_to_retry(self):
        request = urllib.request.Request("https://api-dev.pitwall-web.jp/rest/expert-notes")
        for error in (TimeoutError("timed out"), ConnectionResetError("reset")):
            with self.subTest(error=type(error).__name__):
                opener = mock.Mock()
                opener.open.side_effect = error
                with mock.patch.object(MODULE.urllib.request, "build_opener", return_value=opener):
                    with self.assertRaises(SystemExit) as caught:
                        MODULE.read_json(request)
                self.assertIn("write status is unknown, do not retry automatically", str(caught.exception))

    def test_wrong_success_status_is_rejected(self):
        server, _ = start_server(response_status=200)
        try:
            run = self.run_cli(
                "--name", "Wrong status", "--content", "Report",
                url=f"http://127.0.0.1:{server.server_port}/rest/expert-notes",
            )
        finally:
            stop_server(server)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("response did not contain data.id", run.stderr)

    def test_invalid_success_json_shape_warns_not_to_retry(self):
        server, _ = start_server(response_body="not-an-object")
        try:
            run = self.run_cli(
                "--name", "Invalid response", "--content", "Report",
                url=f"http://127.0.0.1:{server.server_port}/rest/expert-notes",
            )
        finally:
            stop_server(server)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("write status is unknown, do not retry automatically", run.stderr)
        self.assertNotIn("Traceback", run.stderr)

    def test_invalid_data_shape_is_rejected_without_traceback(self):
        for body in ({"data": None}, {"data": {"id": 123}}, {"data": {"id": ""}}):
            with self.subTest(body=body):
                server, _ = start_server(response_body=body)
                try:
                    run = self.run_cli(
                        "--name", "Invalid data", "--content", "Report",
                        url=f"http://127.0.0.1:{server.server_port}/rest/expert-notes",
                    )
                finally:
                    stop_server(server)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("response did not contain data.id", run.stderr)
                self.assertNotIn("Traceback", run.stderr)

    def test_missing_content_file_has_no_traceback(self):
        run = self.run_cli("--name", "Missing", "--content-file", "/does/not/exist.md", "--dry-run")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("Cannot read content file", run.stderr)
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
