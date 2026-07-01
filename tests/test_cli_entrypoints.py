import json
import os
import subprocess
import sys
from unittest.mock import patch

from typer.testing import CliRunner

from securegenomics import __version__
from securegenomics.cli import app


runner = CliRunner()


def test_module_version_exits_zero_without_subcommand():
    env = os.environ.copy()
    src_path = os.path.abspath("src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else os.pathsep.join([src_path, env["PYTHONPATH"]])
    )

    result = subprocess.run(
        [sys.executable, "-m", "securegenomics", "--version"],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert __version__ in result.stdout


def test_runner_version_exits_zero_without_subcommand():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_project_help_shows_one_delete_command():
    result = runner.invoke(app, ["project", "--help"])

    assert result.exit_code == 0
    assert result.output.count("delete") == 1


def test_create_json_alias_outputs_parseable_json_without_banner():
    with (
        patch("securegenomics.cli.ProjectManager") as project_manager,
        patch("securegenomics.cli.CryptoContextManager") as crypto_context_manager,
    ):
        project_manager.return_value.create.return_value = "project-123"
        crypto_context_manager.return_value.generate_upload_crypto_context.return_value = None

        result = runner.invoke(
            app,
            ["create", "--protocol", "alzheimers-risk", "--non-interactive", "--json"],
        )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "success": True,
        "project_id": "project-123",
        "protocol_name": "alzheimers-risk",
        "description": None,
        "crypto_context_ready": True,
    }
