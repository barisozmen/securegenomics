"""
Tests for SecureGenomics manager-level CLI support classes.

These tests keep external boundaries mocked: no live GitHub/server calls and no
real home-directory cache writes.
"""

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from securegenomics.auth import AuthManager
from securegenomics.config import ConfigManager, enforce_https
from securegenomics.local import LocalAnalyzer
from securegenomics.protocol import ProtocolInfo, ProtocolManager


@pytest.fixture(autouse=True)
def isolated_home(tmp_path):
    """Keep all manager cache/config writes inside pytest's temp directory."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        yield tmp_path


class TestConfigManager:
    """Test configuration management."""

    def test_config_manager_initialization(self, isolated_home):
        config_manager = ConfigManager()

        assert config_manager.get_current_user() is None
        assert config_manager.base_config_dir == isolated_home / ".securegenomics"
        assert config_manager.config_dir.name == ".unauthenticated"
        # server_url is NOT a default config key — the server is pinned by
        # get_server_url() and can never be shadowed by config.json.
        assert "server_url" not in config_manager.default_config
        assert config_manager.default_config["github_org"] == "securegenomics"
        assert config_manager.protocols_dir.exists()

    def test_get_config_returns_defaults(self):
        config = ConfigManager().get_config()

        # get_config() never carries a server_url — it's pinned, not merged.
        assert "server_url" not in config
        assert config["github_org"] == "securegenomics"
        assert config["auto_verify_protocols"] is True

    def test_get_config_drops_file_planted_server_url(self, monkeypatch):
        # A config.json with a server_url must NOT surface as authoritative.
        monkeypatch.delenv("SECUREGENOMICS_SERVER_URL", raising=False)
        config_manager = ConfigManager()
        config_manager.config_file.write_text(
            '{"server_url": "https://evil.example", "output_format": "json"}'
        )

        config = config_manager.get_config()

        assert "server_url" not in config
        # Unrelated file overrides still merge as before.
        assert config["output_format"] == "json"
        # The authoritative server URL still comes from the pin.
        assert config_manager.get_server_url() == "https://gencrypt.xyz"

    def test_enforce_https_allows_https_and_loopback_http(self):
        assert enforce_https("https://gencrypt.xyz") == "https://gencrypt.xyz"
        assert enforce_https("http://localhost:8000") == "http://localhost:8000"
        assert enforce_https("http://127.0.0.1:8000") == "http://127.0.0.1:8000"

    def test_enforce_https_rejects_non_loopback_http(self):
        with pytest.raises(ValueError, match="HTTPS is required"):
            enforce_https("http://example.com")

    def test_get_server_url_is_pinned_without_env_override(self, monkeypatch):
        # Fresh temp HOME (isolated_home) and NO env override -> pinned default.
        monkeypatch.delenv("SECUREGENOMICS_SERVER_URL", raising=False)

        assert ConfigManager().get_server_url() == "https://gencrypt.xyz"

    def test_get_server_url_ignores_stale_config_json(self, monkeypatch):
        # A per-user config.json can NEVER misdirect the CLI: the server URL is
        # not sourced from it at all.
        monkeypatch.delenv("SECUREGENOMICS_SERVER_URL", raising=False)
        config_manager = ConfigManager()
        config_manager.config_file.write_text('{"server_url": "https://evil.example"}')

        assert config_manager.get_server_url() == "https://gencrypt.xyz"

    def test_get_server_url_env_override_is_honored(self, monkeypatch):
        monkeypatch.setenv("SECUREGENOMICS_SERVER_URL", "https://staging.example")

        assert ConfigManager().get_server_url() == "https://staging.example"

    def test_get_server_url_env_override_rejects_non_loopback_http(self, monkeypatch):
        monkeypatch.setenv("SECUREGENOMICS_SERVER_URL", "http://evil.example")

        with pytest.raises(ValueError, match="HTTPS is required"):
            ConfigManager().get_server_url()

    def test_get_server_url_env_override_allows_loopback_http(self, monkeypatch):
        monkeypatch.setenv("SECUREGENOMICS_SERVER_URL", "http://127.0.0.1:4700")

        assert ConfigManager().get_server_url() == "http://127.0.0.1:4700"

    def test_authenticated_user_directories_are_separate(self):
        config_manager = ConfigManager()

        unauthenticated_dir = config_manager.config_dir

        config_manager.set_authenticated_user("alice@example.com")
        alice_dir = config_manager.config_dir

        config_manager.set_authenticated_user("bob@example.com")
        bob_dir = config_manager.config_dir

        assert config_manager.get_current_user() == "bob@example.com"
        assert unauthenticated_dir != alice_dir != bob_dir
        assert "alice" in str(alice_dir)
        assert "bob" in str(bob_dir)
        assert unauthenticated_dir.name == ".unauthenticated"

    def test_authentication_persistence_uses_latest_valid_token(self, isolated_home):
        base_config_dir = isolated_home / ".securegenomics"
        alice_dir = base_config_dir / "alice_c160f8cc"
        bob_dir = base_config_dir / "bob_4b9bb806"
        alice_dir.mkdir(parents=True)
        bob_dir.mkdir(parents=True)

        (alice_dir / "auth.json").write_text(
            '{"email": "alice@example.com", "expires_at": %s}' % (time.time() + 3600)
        )
        (bob_dir / "auth.json").write_text(
            '{"email": "bob@example.com", "expires_at": %s}' % (time.time() + 7200)
        )

        config_manager = ConfigManager()

        assert config_manager.get_current_user() == "bob@example.com"
        assert config_manager.config_dir.name == "bob_4b9bb806"


class TestNonDefaultServerWarning:
    """The CLI must surface (once) when pointed at a non-gencrypt server."""

    def test_warns_once_for_non_default_server(self, monkeypatch):
        import securegenomics.config as config_mod

        monkeypatch.setattr(config_mod, "_non_default_server_warned", False)
        monkeypatch.setenv("SECUREGENOMICS_SERVER_URL", "https://staging.example")

        with patch.object(config_mod, "console") as console:
            config_mod.warn_if_non_default_server()
            config_mod.warn_if_non_default_server()  # second call is a no-op

        assert console.print.call_count == 1
        message = console.print.call_args[0][0]
        assert "staging.example" in message
        assert "non-default" in message.lower()

    def test_does_not_warn_for_default_server(self, monkeypatch):
        import securegenomics.config as config_mod

        monkeypatch.setattr(config_mod, "_non_default_server_warned", False)
        monkeypatch.delenv("SECUREGENOMICS_SERVER_URL", raising=False)

        with patch.object(config_mod, "console") as console:
            config_mod.warn_if_non_default_server()

        console.print.assert_not_called()


class TestAuthManager:
    """Test authentication management."""

    def test_auth_manager_initialization(self):
        auth_manager = AuthManager()

        assert auth_manager.server_url == "https://gencrypt.xyz"
        assert auth_manager.auth_file.name == "auth.json"

    def test_is_authenticated_returns_false_when_no_tokens(self):
        auth_manager = AuthManager()

        with patch.object(auth_manager, "_load_tokens", return_value=None):
            assert not auth_manager.is_authenticated()


class TestProtocolManager:
    """Test protocol management."""

    def test_protocol_manager_initialization(self, isolated_home):
        protocol_manager = ProtocolManager()

        assert protocol_manager.config_manager.get_github_org() == "securegenomics"
        assert protocol_manager.protocols_dir == isolated_home / ".securegenomics" / ".unauthenticated" / "protocols"

    def test_list_protocols_uses_github_adapter(self):
        github_client = Mock()
        github_client.list_protocol_repos.return_value = [
            {
                "name": "protocol-alzheimers-risk",
                "description": "Repository fallback description",
                "clone_url": "https://github.com/securegenomics/protocol-alzheimers-risk.git",
                "default_branch": "main",
                "archived": False,
            }
        ]
        github_client.get_protocol_metadata.return_value = {
            "description": "Alzheimer's disease risk analysis",
            "version": "0.2.0",
            "analysis_type": "risk",
            "modes": ["local"],
        }

        with patch("securegenomics.protocol.get_github_client", return_value=github_client):
            protocols = ProtocolManager().list_protocols()

        assert protocols == [
            ProtocolInfo(
                name="alzheimers-risk",
                description="Alzheimer's disease risk analysis",
                github_url="https://github.com/securegenomics/protocol-alzheimers-risk.git",
                commit_hash="main",
                version="0.2.0",
                analysis_type="risk",
                local_supported=True,
                aggregated_supported=False,
            )
        ]
        github_client.list_protocol_repos.assert_called_once_with()
        github_client.get_protocol_metadata.assert_called_once_with("alzheimers-risk")

    def test_verify_accepts_matching_remote_hash_and_valid_structure(self, tmp_path):
        protocol_dir = tmp_path / "test-protocol"
        protocol_dir.mkdir()
        github_client = Mock()
        github_client.get_latest_commit_hash.return_value = "abc123def456"

        protocol_manager = ProtocolManager()
        with (
            patch.object(protocol_manager.config_manager, "get_protocol_cache_dir", return_value=protocol_dir),
            patch("securegenomics.protocol.get_github_client", return_value=github_client),
            patch("securegenomics.protocol.subprocess.run", return_value=Mock(returncode=0, stdout="abc123def456\n")),
            patch.object(protocol_manager, "_verify_protocol_structure", return_value=(True, [])),
        ):
            assert protocol_manager.verify("test-protocol") is True

        github_client.get_latest_commit_hash.assert_called_once_with("protocol-test-protocol")

    def test_verify_allows_offline_hash_when_structure_is_valid(self, tmp_path):
        protocol_dir = tmp_path / "test-protocol"
        protocol_dir.mkdir()
        github_client = Mock()
        github_client.get_latest_commit_hash.return_value = None

        protocol_manager = ProtocolManager()
        with (
            patch.object(protocol_manager.config_manager, "get_protocol_cache_dir", return_value=protocol_dir),
            patch("securegenomics.protocol.get_github_client", return_value=github_client),
            patch("securegenomics.protocol.subprocess.run", return_value=Mock(returncode=0, stdout="abc123def456\n")),
            patch.object(protocol_manager, "_verify_protocol_structure", return_value=(True, [])),
        ):
            assert protocol_manager.verify("test-protocol") is True

    def test_verify_protocol_structure_returns_errors_for_invalid_protocol(self, tmp_path):
        protocol_manager = ProtocolManager()

        valid, errors = protocol_manager._verify_protocol_structure(tmp_path)

        assert valid is False
        assert errors == ["Missing required file: protocol.yaml"]

    def test_verify_protocol_structure_supports_local_only_protocols(self, tmp_path):
        (tmp_path / "protocol.yaml").write_text(
            "name: demo\n"
            "description: Demo protocol\n"
            "modes:\n"
            "  - local\n"
        )
        (tmp_path / "local_compute.py").write_text("def local_compute(**kwargs): return 1\n")

        valid, errors = ProtocolManager()._verify_protocol_structure(tmp_path)

        assert valid is True
        assert errors == []


class TestLocalAnalyzer:
    """Test local analysis functionality."""

    def test_local_analyzer_initialization(self):
        analyzer = LocalAnalyzer()

        assert analyzer.config_manager is not None
        assert analyzer.protocol_manager is not None

    def test_analyze_requires_existing_vcf_before_protocol_execution(self, tmp_path):
        analyzer = LocalAnalyzer()
        missing_vcf = tmp_path / "missing.vcf"

        with (
            patch.object(analyzer.protocol_manager, "fetch") as fetch,
            patch.object(analyzer.protocol_manager, "verify") as verify,
            patch.object(analyzer.protocol_manager, "execute") as execute,
            pytest.raises(Exception, match="VCF file not found"),
        ):
            analyzer.analyze("demo", missing_vcf)

        fetch.assert_not_called()
        verify.assert_not_called()
        execute.assert_not_called()

    def test_analyze_runs_local_compute_then_interpret_without_fetch_when_cached(self, tmp_path):
        analyzer = LocalAnalyzer()
        vcf_path = tmp_path / "sample.vcf"
        vcf_path.write_text("not parsed by current LocalAnalyzer contract\n")
        analyzer.config_manager.get_protocol_cache_dir("demo").mkdir(parents=True)

        with (
            patch.object(analyzer.protocol_manager, "fetch") as fetch,
            patch.object(analyzer.protocol_manager, "verify", return_value=True) as verify,
            patch.object(analyzer.protocol_manager, "execute", side_effect=["prs-score", "interpreted result"]) as execute,
            patch("securegenomics.local.print") as print_mock,
        ):
            analyzer.analyze("demo", vcf_path)

        fetch.assert_not_called()
        verify.assert_called_once_with("demo")
        assert execute.call_args_list[0].kwargs == {
            "protocol_name": "demo",
            "operation": "local_compute",
            "vcf_path": str(vcf_path),
        }
        assert execute.call_args_list[1].kwargs == {
            "protocol_name": "demo",
            "operation": "local_interpret",
            "prs": "prs-score",
        }
        print_mock.assert_called_once_with("interpreted result")

    def test_list_local_protocols_filters_protocols_by_local_support(self):
        analyzer = LocalAnalyzer()
        protocols = [
            ProtocolInfo(
                name="local-demo",
                description="",
                github_url="https://example.test/local-demo.git",
                commit_hash="main",
                local_supported=True,
            ),
            ProtocolInfo(
                name="aggregate-only",
                description="",
                github_url="https://example.test/aggregate-only.git",
                commit_hash="main",
                local_supported=False,
            ),
        ]

        with patch.object(analyzer.protocol_manager, "list_protocols", return_value=protocols):
            assert analyzer.list_local_protocols() == ["local-demo"]


class TestCLIIntegration:
    """Integration tests for CLI-adjacent manager behavior."""

    def test_system_clear_cache_command(self, isolated_home):
        config_manager = ConfigManager()
        base_cache_dir = config_manager.base_config_dir

        user_dir = base_cache_dir / "testuser_123"
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "auth.json").write_text("{}")
        protocol_dir = base_cache_dir / ".unauthenticated" / "protocols" / "test-protocol"
        protocol_dir.mkdir(parents=True, exist_ok=True)
        (protocol_dir / "manifest.json").write_text("{}")

        with patch("rich.prompt.Confirm.ask", return_value=True):
            from securegenomics.cli import system_clear_cache

            try:
                system_clear_cache()
            except SystemExit:
                pass

        assert base_cache_dir.exists()
        assert not user_dir.exists()
        assert not protocol_dir.exists()
        assert (base_cache_dir / ".unauthenticated" / "protocols").exists()
        assert (base_cache_dir / ".unauthenticated" / "crypto_context").exists()
        assert (base_cache_dir / ".unauthenticated" / "projects").exists()
