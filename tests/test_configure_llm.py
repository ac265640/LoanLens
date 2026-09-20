"""
scripts/configure_llm.sh: the API key must reach SSM without ever appearing on a
command line or in output, and every failure path must write nothing.

Runs the real script against a fake OpenAI-compatible provider and a fake `aws`
executable that records its arguments.
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "configure_llm.sh"
KEY = "sk-SECRET-key-987654321"

FAKE_AWS = """#!/usr/bin/env bash
python3 - "$@" <<'PY'
import json, os, sys
argv = sys.argv[1:]
rec = {"argv": argv}
for a in argv:
    if a.startswith("file://"):
        rec["file_content"] = open(a[7:]).read()
with open(os.environ["FAKE_AWS_LOG"], "a") as f:
    f.write(json.dumps(rec) + "\\n")
PY
"""


class _Provider(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "bad key"})
        self._send(200, {"data": [{"id": "models/" + m} for m in self.server.state["models"]]})  # gemini-style ids

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.server.state["chat_status"] != 200:
            return self._send(self.server.state["chat_status"], {"error": "nope"})
        self._send(200, {"choices": [{"message": {"content": "OK"}}]})

    def log_message(self, *args):
        pass


@pytest.fixture
def provider():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    srv.state = {"models": ["other-model", "test-model"], "chat_status": 200}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    yield srv
    srv.shutdown()


@pytest.fixture
def run(tmp_path, provider):
    shim = tmp_path / "aws"
    shim.write_text(FAKE_AWS)
    shim.chmod(0o755)
    log = tmp_path / "aws.log"

    def _run(key=KEY):
        env = {
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "FAKE_AWS_LOG": str(log),
            "LLM_BASE_URL": provider.base,
            "LLM_MODEL": "test-model",
            "AWS_REGION": "us-east-1",
        }
        proc = subprocess.run(["bash", str(SCRIPT), "custom"], input=key + "\n", capture_output=True, text=True, env=env, timeout=60)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return proc, calls

    return _run


def _by_name(calls):
    return {c["argv"][c["argv"].index("--name") + 1]: c["argv"][c["argv"].index("--type") + 1] for c in calls}


def test_success_stores_three_parameters_with_the_right_types(run):
    proc, calls = run()
    assert proc.returncode == 0, proc.stderr
    assert _by_name(calls) == {
        "/loanlens/llm/api_key": "SecureString",
        "/loanlens/llm/base_url": "String",
        "/loanlens/llm/model": "String",
    }
    assert "Using model: test-model" in proc.stdout  # picked from the provider's list, 'models/' prefix stripped


def test_the_key_reaches_aws_only_through_a_file_never_argv_or_output(run):
    proc, calls = run()
    key_call = next(c for c in calls if "file_content" in c)
    assert key_call["file_content"] == KEY
    assert all(KEY not in " ".join(c["argv"]) for c in calls)
    assert KEY not in proc.stdout + proc.stderr


def test_a_rejected_key_fails_clearly_and_writes_nothing(run):
    proc, calls = run(key="wrong-key")
    assert proc.returncode != 0 and "rejected the key" in proc.stderr
    assert calls == []


def test_an_unavailable_model_lists_what_is_available_and_writes_nothing(run, provider):
    provider.state["models"] = ["something-else"]
    proc, calls = run()
    assert proc.returncode != 0 and "something-else" in proc.stderr
    assert calls == []


def test_a_failing_test_request_writes_nothing(run, provider):
    provider.state["chat_status"] = 500
    proc, calls = run()
    assert proc.returncode != 0 and "test request failed" in proc.stderr
    assert calls == []
