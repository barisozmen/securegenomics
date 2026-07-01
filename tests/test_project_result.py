from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from securegenomics.project import ProjectManager


@pytest.fixture(autouse=True)
def isolated_home(tmp_path):
    with patch("pathlib.Path.home", return_value=tmp_path):
        yield tmp_path


class FakeResultResponse:
    def __init__(self, status_code=200, json_data=None, content=None, headers=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content if content is not None else b"{...}"
        self.headers = headers or {"content-type": "application/json"}
        self.text = ""

    def json(self):
        return self._json


def test_get_result_processes_json_encrypted_payload(isolated_home):
    pm = ProjectManager()
    pm.server_url = "https://gencrypt.example"

    context_dir = isolated_home / "crypto-context"
    context_dir.mkdir()
    encrypted_path = Path("/tmp/encrypted-result.bin")
    decrypted_path = Path("/tmp/decrypted-result.json")
    interpreted_path = Path("/tmp/interpreted-result.json")
    response = FakeResultResponse(
        json_data={"encrypted": True, "data": "000102"},
        headers={"content-type": "application/json"},
    )

    def execute_protocol(*, protocol_name, operation, **kwargs):
        assert protocol_name == "demo"
        if operation == "decrypt_result":
            assert kwargs == {
                "encrypted_results": b"\x00\x01\x02",
                "private_crypto_context": b"private-context",
            }
            return {"raw": 7}
        if operation == "interpret_result":
            assert kwargs == {"result": {"raw": 7}}
            return {"answer": 42}
        raise AssertionError(f"unexpected operation: {operation}")

    with (
        patch("securegenomics.project_result.requests.get", return_value=response) as get,
        patch.object(
            pm.auth_manager,
            "_get_auth_headers",
            return_value={"Authorization": "Bearer token"},
        ),
        patch.object(pm, "_get_project_info", return_value={"protocol_name": "demo"}),
        patch.object(pm, "get_job_status", side_effect=AssertionError("unused")),
        patch.object(pm.config_manager, "get_crypto_context_dir", return_value=context_dir),
        patch.object(
            pm.fhe_manager,
            "load_context",
            return_value=(b"public-context", b"private-context"),
        ),
        patch.object(pm.protocol_manager, "execute", side_effect=execute_protocol),
        patch.object(pm, "_save_encrypted_result", return_value=encrypted_path) as save_encrypted,
        patch.object(pm, "_save_decrypted_result", return_value=decrypted_path) as save_decrypted,
        patch.object(
            pm,
            "_save_interpreted_result",
            return_value=interpreted_path,
        ) as save_interpreted,
        patch.object(pm.config_manager, "log_audit_event") as log_audit_event,
    ):
        result = pm.get_result("proj-1")

    get.assert_called_once_with(
        "https://gencrypt.example/api/result",
        params={"project_id": "proj-1"},
        headers={"Authorization": "Bearer token"},
        timeout=30,
        allow_redirects=False,
    )
    save_encrypted.assert_called_once_with("proj-1", b"\x00\x01\x02")
    save_decrypted.assert_called_once_with("proj-1", {"raw": 7})
    save_interpreted.assert_called_once_with("proj-1", result)
    log_audit_event.assert_called_once_with(
        "project_result",
        {
            "project_id": "proj-1",
            "protocol_name": "demo",
            "decrypted": True,
            "saved_to": str(encrypted_path),
            "decrypted_saved_to": str(decrypted_path),
        },
    )
    assert result == {
        "answer": 42,
        "_metadata": {
            "encrypted_result_saved_to": str(encrypted_path),
            "decrypted_result_saved_to": str(decrypted_path),
            "encrypted_size_bytes": 3,
            "project_id": "proj-1",
            "protocol_name": "demo",
        },
    }
