"""
Tests for SecureGenomics CLI.

Basic smoke tests to verify the CLI implementation works correctly.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from securegenomics.config import ConfigManager
from securegenomics.auth import AuthManager
from securegenomics.protocol import ProtocolManager, ProtocolInfo
from securegenomics.local import LocalAnalyzer
from securegenomics.cli import main


class TestConfigManager:
    """Test configuration management."""
    
    def test_config_manager_initialization(self):
        """Test that ConfigManager initializes correctly."""
        config_manager = ConfigManager()
        
        # Should start unauthenticated
        assert config_manager.get_current_user() is None
        assert config_manager.config_dir.name == ".unauthenticated"
        assert config_manager.default_config["server_url"] == "http://127.0.0.1:8000"
        assert config_manager.default_config["github_org"] == "securegenomics"
    
    def test_get_config_returns_defaults(self):
        """Test that get_config returns default configuration."""
        config_manager = ConfigManager()
        config = config_manager.get_config()
        
        assert "server_url" in config
        assert "github_org" in config
        assert config["server_url"] == "http://127.0.0.1:8000"

    def test_authenticated_user_directories(self):
        """Test that authenticated users get separate directories."""
        config_manager = ConfigManager()
        
        # Initially unauthenticated
        assert config_manager.get_current_user() is None
        unauthenticated_dir = config_manager.config_dir
        
        # Set authenticated user
        config_manager.set_authenticated_user("alice@example.com")
        assert config_manager.get_current_user() == "alice@example.com"
        alice_dir = config_manager.config_dir
        
        # Set different authenticated user
        config_manager.set_authenticated_user("bob@example.com")
        assert config_manager.get_current_user() == "bob@example.com"
        bob_dir = config_manager.config_dir
        
        # All directories should be different
        assert unauthenticated_dir != alice_dir
        assert alice_dir != bob_dir
        assert unauthenticated_dir != bob_dir
        
        # Should contain sanitized usernames
        assert "alice" in str(alice_dir)
        assert "bob" in str(bob_dir)
        assert ".unauthenticated" in str(unauthenticated_dir)

    def test_authentication_persistence(self):
        """Test that authentication persists across ConfigManager instances."""
        import tempfile
        import json
        import time
        from unittest.mock import patch
        
        # Create a temporary config directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_base_dir = Path(temp_dir) / ".securegenomics"
            temp_base_dir.mkdir()
            
            # Create a user directory with valid auth tokens
            user_dir = temp_base_dir / "alice_c160f8cc"
            user_dir.mkdir()
            auth_file = user_dir / "auth.json"
            
            # Create valid tokens (expires in 1 hour)
            tokens = {
                "email": "alice@example.com",
                "access_token": "fake_token",
                "refresh_token": "fake_refresh",
                "expires_at": time.time() + 3600  # 1 hour from now
            }
            
            with open(auth_file, 'w') as f:
                json.dump(tokens, f)
            
            # Patch the home directory to use our temp directory
            with patch('pathlib.Path.home', return_value=Path(temp_dir)):
                # First ConfigManager instance should find the user
                cm1 = ConfigManager()
                assert cm1.get_current_user() == "alice@example.com"
                assert "alice_c160f8cc" in str(cm1.config_dir)
                
                # Second ConfigManager instance should also find the same user
                cm2 = ConfigManager()
                assert cm2.get_current_user() == "alice@example.com"
                assert cm1.config_dir == cm2.config_dir


class TestAuthManager:
    """Test authentication management."""
    
    def test_auth_manager_initialization(self):
        """Test that AuthManager initializes correctly."""
        auth_manager = AuthManager()
        
        assert auth_manager.server_url == "http://127.0.0.1:8000"
        assert auth_manager.auth_file.name == "auth.json"
    
    def test_is_authenticated_returns_false_when_no_tokens(self):
        """Test that is_authenticated returns False when no tokens exist."""
        auth_manager = AuthManager()
        
        # Mock _load_tokens to return None (no tokens)
        with patch.object(auth_manager, '_load_tokens', return_value=None):
            assert not auth_manager.is_authenticated()


class TestProtocolManager:
    """Test protocol management."""
    
    def test_protocol_manager_initialization(self):
        """Test that ProtocolManager initializes correctly."""
        protocol_manager = ProtocolManager()
        
        assert protocol_manager.github_org == "securegenomics"
        assert protocol_manager.github_api_base == "https://api.github.com"
    
    @patch('requests.get')
    def test_list_protocols_with_mock_response(self, mock_get):
        """Test listing protocols with mocked GitHub response."""
        # Mock GitHub API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "name": "protocol-alzheimers-risk",
                "description": "Alzheimer's disease risk analysis",
                "clone_url": "https://github.com/securegenomics/protocol-alzheimers-risk.git",
                "default_branch": "main",
                "archived": False
            }
        ]
        mock_get.return_value = mock_response
        
        protocol_manager = ProtocolManager()
        
        # Mock the _get_protocol_metadata method
        with patch.object(protocol_manager, '_get_protocol_metadata') as mock_metadata:
            mock_metadata.return_value = ProtocolInfo(
                name="alzheimers-risk",
                description="Alzheimer's disease risk analysis",
                github_url="https://github.com/securegenomics/protocol-alzheimers-risk.git",
                commit_hash="main"
            )
            
            protocols = protocol_manager.list_protocols()
            
            assert len(protocols) == 1
            assert protocols[0].name == "alzheimers-risk"
            assert protocols[0].description == "Alzheimer's disease risk analysis"


class TestLocalAnalyzer:
    """Test local analysis functionality."""
    
    def test_local_analyzer_initialization(self):
        """Test that LocalAnalyzer initializes correctly."""
        analyzer = LocalAnalyzer()
        
        assert analyzer.config_manager is not None
        assert analyzer.protocol_manager is not None
    
    def test_is_valid_vcf_with_invalid_file(self, tmp_path):
        """Test VCF validation with invalid file."""
        analyzer = LocalAnalyzer()
        
        # Create invalid VCF file
        invalid_vcf = tmp_path / "invalid.vcf"
        invalid_vcf.write_text("This is not a VCF file")
        
        assert not analyzer._is_valid_vcf(invalid_vcf)
    
    def test_is_valid_vcf_with_valid_file(self, tmp_path):
        """Test VCF validation with valid file."""
        analyzer = LocalAnalyzer()
        
        # Create minimal valid VCF file
        valid_vcf_content = """##fileformat=VCFv4.2
##contig=<ID=1,length=249250621>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SAMPLE1
1	14370	rs6054257	G	A	29	PASS	.	GT	0|0
"""
        valid_vcf = tmp_path / "valid.vcf"
        valid_vcf.write_text(valid_vcf_content)
        
        assert analyzer._is_valid_vcf(valid_vcf)


class TestCLIIntegration:
    """Integration tests for CLI components."""
    
    @patch('subprocess.run')
    def test_protocol_verification_with_mock_git(self, mock_run):
        """Test protocol verification with mocked git command."""
        # Mock git rev-parse command
        mock_run.return_value = Mock(
            returncode=0,
            stdout="abc123def456\n"
        )
        
        protocol_manager = ProtocolManager()
        
        # Create mock protocol directory
        with patch.object(protocol_manager.config_manager, 'get_protocol_cache_dir') as mock_dir:
            mock_protocol_dir = Mock()
            mock_protocol_dir.exists.return_value = True
            mock_dir.return_value = mock_protocol_dir
            
            # Mock protocol structure verification
            with patch.object(protocol_manager, '_verify_protocol_structure', return_value=True):
                # Mock network request for remote hash
                with patch('requests.get') as mock_get:
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"sha": "abc123def456"}
                    mock_get.return_value = mock_response
                    
                    result = protocol_manager.verify("test-protocol")
                    assert result is True

    def test_system_clear_cache_command(self, tmp_path):
        """Test the 'system clear-cache' command."""
        # Use a temporary directory as the home directory for this test
        with patch('pathlib.Path.home', return_value=tmp_path):
            # Initialize ConfigManager to set up the .securegenomics directory
            config_manager = ConfigManager()
            base_cache_dir = config_manager.base_config_dir
            assert base_cache_dir.exists()

            # Create some dummy files and directories in the cache
            user_dir = base_cache_dir / "testuser_123"
            user_dir.mkdir(parents=True, exist_ok=True)
            (user_dir / "auth.json").write_text("{}")
            protocol_dir = base_cache_dir / ".unauthenticated" / "protocols" / "test-protocol"
            protocol_dir.mkdir(parents=True, exist_ok=True)
            (protocol_dir / "manifest.json").write_text("{}")

            assert (user_dir / "auth.json").exists()
            assert (protocol_dir / "manifest.json").exists()

            # Mock typer.confirm to automatically say "yes"
            with patch('rich.prompt.Confirm.ask', return_value=True):
                # Run the clear-cache command
                # We need to simulate how Typer calls the command function.
                # Directly calling system_clear_cache() from cli.py
                from securegenomics.cli import system_clear_cache
                try:
                    system_clear_cache()
                except SystemExit: # Typer raises SystemExit on successful command completion
                    pass


            # Verify the base cache directory still exists (it should be recreated)
            assert base_cache_dir.exists()

            # Verify that the dummy files/dirs are gone
            assert not (user_dir / "auth.json").exists()
            assert not user_dir.exists() # The user-specific directory should be gone
            assert not (protocol_dir / "manifest.json").exists()
            assert not protocol_dir.exists() # The protocol directory should be gone

            # Verify that essential subdirectories are recreated (e.g., .unauthenticated)
            assert (base_cache_dir / ".unauthenticated").exists()
            assert (base_cache_dir / ".unauthenticated" / "protocols").exists()
            assert (base_cache_dir / ".unauthenticated" / "crypto_context").exists()
            assert (base_cache_dir / ".unauthenticated" / "projects").exists()


if __name__ == "__main__":
    pytest.main([__file__]) 