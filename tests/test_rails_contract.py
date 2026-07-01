"""
Tests for the Gencrypt (Rails) API contract the CLI must consume.

Covers the reconciliation points from RFC 0001:
  - error parsing of the Rails {error:{code,message,details}} shape,
  - login/register token parsing (opaque token + expires_in, no jwt.decode),
  - unwrapping of body["project"] / body["job"],
  - list pagination.count,
  - graceful degradation of stop/delete_profile.

All network boundaries are mocked; nothing touches the real server or the real
home directory.
"""

import time
from unittest.mock import Mock, patch

import pytest

from securegenomics.auth import AuthManager
from securegenomics.project import ProjectManager


@pytest.fixture(autouse=True)
def isolated_home(tmp_path):
    """Keep all manager cache/config/auth writes inside pytest's temp dir."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        yield tmp_path


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, json_data=None, content=None, text=""):
        self.status_code = status_code
        self._json = json_data
        # Callers that gate on `response.content` (e.g. _handle_api_response)
        # need a truthy body whenever there is JSON to parse.
        if content is None:
            content = b"{...}" if json_data is not None else b""
        self.content = content
        self.text = text
        self.headers = {}

    def json(self):
        if self._json is None:
            raise ValueError("response is not JSON")
        return self._json


def _stored_tokens(am):
    """Read the persisted auth.json via the manager's live config path.

    After login the token file is migrated into the authenticated-user dir, so
    the stored path lives on config_manager.auth_file (a fresh AuthManager in a
    later command would resolve the same file).
    """
    import json
    path = am.config_manager.auth_file
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# _parse_error_response / _parse_error_code — Rails {error:{code,message}} shape
# ---------------------------------------------------------------------------

class TestErrorParsing:
    def test_parses_rails_error_message(self):
        am = AuthManager()
        resp = FakeResponse(401, {"error": {"code": "invalid_credentials",
                                            "message": "Invalid email or password."}})
        assert am._parse_error_response(resp) == "Invalid email or password."

    def test_exposes_rails_error_code(self):
        am = AuthManager()
        resp = FakeResponse(409, {"error": {"code": "duplicate_filename",
                                            "message": "already uploaded"}})
        assert am._parse_error_code(resp) == "duplicate_filename"

    def test_flattens_rails_details(self):
        am = AuthManager()
        resp = FakeResponse(422, {"error": {
            "code": "validation_failed",
            "message": "Validation failed",
            "details": {"email": ["is invalid"], "password": ["is too short"]},
        }})
        message = am._parse_error_response(resp)
        assert "Validation failed" in message
        assert "email: is invalid" in message
        assert "password: is too short" in message

    def test_error_code_is_none_for_non_rails_body(self):
        am = AuthManager()
        # DRF-style body (github.py) has no error.code.
        resp = FakeResponse(400, {"detail": "Bad request"})
        assert am._parse_error_code(resp) is None
        assert am._parse_error_response(resp) == "Bad request"

    def test_drf_fallback_field_arrays(self):
        am = AuthManager()
        resp = FakeResponse(400, {"non_field_errors": ["Something went wrong"]})
        assert am._parse_error_response(resp) == "Something went wrong"

    def test_non_json_body_degrades_gracefully(self):
        am = AuthManager()
        resp = FakeResponse(500, json_data=None, text="upstream boom")
        msg = am._parse_error_response(resp)
        assert "500" in msg
        assert am._parse_error_code(resp) is None


# ---------------------------------------------------------------------------
# login / register — opaque token + expires_in (no jwt.decode)
# ---------------------------------------------------------------------------

class TestTokenParsing:
    TOKEN_BODY = {
        "token": "opaque-signed-session-id",
        "access_token": "opaque-signed-session-id",
        "token_type": "Bearer",
        "expires_in": 2592000,
        "user": {"id": 1, "email": "alice@example.com",
                 "email_address": "alice@example.com", "username": "alice"},
    }

    def test_login_stores_opaque_token_and_expiry(self):
        am = AuthManager()
        before = time.time()
        with patch("securegenomics.auth.requests.post",
                   return_value=FakeResponse(201, self.TOKEN_BODY)) as post:
            assert am.login("alice@example.com", "pw") is True

        post.assert_called_once()
        tokens = _stored_tokens(am)
        assert tokens["access_token"] == "opaque-signed-session-id"
        # Expiry derived from expires_in, not a decoded JWT.
        assert before + 2592000 - 5 <= tokens["expires_at"] <= time.time() + 2592000 + 5
        # No refresh concept survives.
        assert "refresh_token" not in tokens
        assert tokens["email"] == "alice@example.com"

    def test_login_accepts_200_too(self):
        am = AuthManager()
        with patch("securegenomics.auth.requests.post",
                   return_value=FakeResponse(200, self.TOKEN_BODY)):
            assert am.login("alice@example.com", "pw") is True

    def test_login_reads_token_key_or_access_token(self):
        am = AuthManager()
        body = {"access_token": "only-access-token", "expires_in": 100,
                "user": {"email": "bob@example.com"}}
        with patch("securegenomics.auth.requests.post",
                   return_value=FakeResponse(201, body)):
            assert am.login("bob@example.com", "pw") is True
        assert _stored_tokens(am)["access_token"] == "only-access-token"

    def test_register_stores_token_without_second_login(self):
        am = AuthManager()
        with patch("securegenomics.auth.requests.post",
                   return_value=FakeResponse(201, self.TOKEN_BODY)) as post:
            assert am.register("alice@example.com", "password123") is True

        # Exactly one POST — no login() round-trip after register.
        post.assert_called_once()
        assert _stored_tokens(am)["access_token"] == "opaque-signed-session-id"

    def test_login_raises_rails_error_message(self):
        am = AuthManager()
        err = FakeResponse(401, {"error": {"code": "invalid_credentials",
                                           "message": "Invalid email or password."}})
        with patch("securegenomics.auth.requests.post", return_value=err):
            with pytest.raises(Exception, match="Invalid email or password."):
                am.login("alice@example.com", "wrong")

    def test_get_token_returns_none_when_expired(self):
        am = AuthManager()
        # Store an already-expired token directly.
        am._save_tokens({"access_token": "t", "email": "x@example.com",
                         "expires_at": time.time() - 10})
        assert am.get_token() is None


# ---------------------------------------------------------------------------
# ProjectManager — unwrapping body["project"] / body["job"] + pagination.count
# ---------------------------------------------------------------------------

class TestProjectContract:
    def test_create_reads_nested_project_id(self):
        pm = ProjectManager()
        body = {"project": {"id": "proj-123", "protocol_name": "demo",
                            "has_context": False}}
        with patch.object(pm, "_make_api_request",
                          return_value=FakeResponse(201, body)):
            assert pm.create("demo") == "proj-123"

    def test_run_reads_nested_job_id(self):
        pm = ProjectManager()
        body = {"job": {"id": "job-456", "status": "pending"}}
        with patch.object(pm, "_make_api_request",
                          return_value=FakeResponse(201, body)):
            assert pm.run("proj-123") == "job-456"

    def test_get_project_info_unwraps_project(self):
        pm = ProjectManager()
        body = {"project": {"id": "proj-1", "protocol_name": "demo",
                            "has_context": True}}
        with patch.object(pm, "_make_api_request",
                          return_value=FakeResponse(200, body)):
            info = pm._get_project_info("proj-1")
        assert info["protocol_name"] == "demo"
        assert info["has_context"] is True
        assert "project" not in info

    def test_list_projects_reads_pagination_count(self):
        pm = ProjectManager()
        body = {
            "projects": [{"id": "p1", "protocol_name": "demo"},
                         {"id": "p2", "protocol_name": "demo"}],
            "pagination": {"page": 1, "per_page": 100, "count": 7, "total_pages": 1},
        }
        with patch.object(pm, "_make_api_request",
                          return_value=FakeResponse(200, body)):
            result = pm.list_projects(detailed=True)
        assert result["count"] == 7
        assert len(result["projects"]) == 2

    def test_list_projects_basic_annotates_status(self):
        pm = ProjectManager()
        body = {
            "projects": [{"id": "p1", "protocol_name": "demo"}],
            "pagination": {"count": 1},
        }
        with (
            patch.object(pm, "_make_api_request", return_value=FakeResponse(200, body)),
            patch.object(pm, "_get_project_status", return_value="completed"),
        ):
            projects = pm.list_projects(detailed=False)
        assert projects[0]["status"] == "completed"

    def test_stop_degrades_gracefully(self):
        pm = ProjectManager()
        with pytest.raises(Exception, match="isn't supported yet"):
            pm.stop("proj-123")

    def test_add_member_returns_granted_member(self):
        pm = ProjectManager()
        body = {"membership": {"id": 5, "project_id": "proj-1",
                               "user": {"id": 9, "email": "bob@example.com"},
                               "role": "member"}}
        with patch.object(pm, "_make_api_request",
                          return_value=FakeResponse(201, body)) as req:
            member = pm.add_member("proj-1", "bob@example.com")

        # Posts email to the slash-less members endpoint.
        args, kwargs = req.call_args
        assert args[0] == "POST"
        assert args[1] == "/api/projects/proj-1/members"
        assert kwargs["json"] == {"email": "bob@example.com"}
        # Returns the granted member ({id, email}).
        assert member == {"id": 9, "email": "bob@example.com"}

    def test_add_member_user_not_found(self):
        pm = ProjectManager()
        resp = FakeResponse(404, {"error": {"code": "user_not_found",
                                            "message": "No such user"}})
        with patch.object(pm, "_make_api_request", return_value=resp):
            with pytest.raises(Exception, match="No Gencrypt account for that email"):
                pm.add_member("proj-1", "ghost@example.com")

    def test_add_member_forbidden_for_non_owner(self):
        pm = ProjectManager()
        resp = FakeResponse(403, {"error": {"code": "forbidden",
                                            "message": "Forbidden"}})
        with patch.object(pm, "_make_api_request", return_value=resp):
            with pytest.raises(Exception, match="Only the project owner can add members"):
                pm.add_member("proj-1", "bob@example.com")


# ---------------------------------------------------------------------------
# whoami / delete_profile / logout
# ---------------------------------------------------------------------------

class TestAuthDegradations:
    def test_whoami_reads_nested_user_email(self):
        am = AuthManager()
        am._save_tokens({"access_token": "t", "email": "cache@example.com",
                         "expires_at": time.time() + 3600})
        profile = FakeResponse(200, {"user": {"email": "server@example.com"}})
        with patch("securegenomics.auth.requests.get", return_value=profile):
            assert am.whoami() == {"email": "server@example.com"}

    def test_whoami_falls_back_to_cached_email(self):
        am = AuthManager()
        am._save_tokens({"access_token": "t", "email": "cache@example.com",
                         "expires_at": time.time() + 3600})
        with patch("securegenomics.auth.requests.get",
                   return_value=FakeResponse(401, {"error": {"code": "unauthorized",
                                                             "message": "nope"}})):
            assert am.whoami() == {"email": "cache@example.com"}

    def test_delete_profile_degrades_without_endpoint(self):
        am = AuthManager()
        # Must not raise, must not hit the network, returns False.
        with patch("securegenomics.auth.requests.post") as post, \
             patch("securegenomics.auth.requests.delete") as delete:
            assert am.delete_profile() is False
            post.assert_not_called()
            delete.assert_not_called()

    def test_logout_calls_server_then_clears_local(self):
        am = AuthManager()
        am._save_tokens({"access_token": "t", "email": "x@example.com",
                         "expires_at": time.time() + 3600})
        with patch("securegenomics.auth.requests.delete",
                   return_value=FakeResponse(204)) as delete:
            am.logout()
        delete.assert_called_once()
        assert am._load_tokens() is None

    def test_logout_ignores_network_errors(self):
        import requests as _requests
        am = AuthManager()
        am._save_tokens({"access_token": "t", "email": "x@example.com",
                         "expires_at": time.time() + 3600})
        with patch("securegenomics.auth.requests.delete",
                   side_effect=_requests.RequestException("boom")):
            am.logout()  # must not raise
        assert am._load_tokens() is None
