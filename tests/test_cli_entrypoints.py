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


def test_project_list_detailed_renders_dict_contributors():
    """Regression: Rails serializes `contributors` as a list of dicts
    ({id, email, username}), not strings. The detailed listing must render
    them without crashing on `', '.join(...)`."""
    detailed_payload = {
        "count": 1,
        "pagination": {"count": 1},
        "projects": [
            {
                "id": "proj-1",
                "protocol_name": "alzheimers-risk",
                "created_at": "2026-06-30T12:00:00Z",
                "job_status": "completed",
                "has_context": True,
                "vcf_count": 2,
                "contributor_count": 2,
                "contributors": [
                    {"id": 1, "email": "alice@example.com", "username": "alice"},
                    {"id": 2, "email": "bob@example.com", "username": "bob"},
                ],
                "latest_job_id": None,
                "latest_job_finished": None,
                "latest_job_created": None,
                "protocol_description": "Alzheimer's disease risk analysis",
            }
        ],
    }

    with patch("securegenomics.cli.ProjectManager") as project_manager:
        project_manager.return_value.list_projects.return_value = detailed_payload

        result = runner.invoke(app, ["project", "list", "--detailed"])

    assert result.exit_code == 0
    assert "alice@example.com" in result.output
    assert "bob@example.com" in result.output


def test_project_logs_renders_rails_event_shape():
    logs_payload = {
        "job": {
            "id": "job-1",
            "project_id": "proj-1",
            "protocol_name": "alzheimers-risk",
            "status": "completed",
            "started_at": "2026-06-30T12:00:00Z",
            "finished_at": "2026-06-30T12:01:03Z",
        },
        "events": [
            {
                "occurred_at": "2026-06-30T12:00:03Z",
                "relative_seconds": 3.2,
                "event_type": "validate",
                "message": "Inputs validated",
            }
        ],
    }

    with patch("securegenomics.cli.ProjectManager") as project_manager:
        project_manager.return_value.get_project_job_logs.return_value = logs_payload

        result = runner.invoke(app, ["project", "logs", "proj-1"])

    assert result.exit_code == 0
    assert "Job ID: job-1" in result.output
    assert "Project: alzheimers-risk (proj-1)" in result.output
    assert "12:00:03 (+3.2s)" in result.output
    assert "validate: Inputs validated" in result.output
    assert "View results: securegenomics project result proj-1" in result.output


def test_project_job_logs_renders_simple_event_shape():
    logs_payload = {
        "job": {
            "id": "job-1",
            "project_id": "proj-1",
            "status": "failed",
            "error_summary": "Protocol failed",
        },
        "events": [
            {
                "occurred_at": "2026-06-30T12:00:03Z",
                "event_type": "error",
                "message": "Boom",
            }
        ],
    }

    with patch("securegenomics.cli.ProjectManager") as project_manager:
        project_manager.return_value.get_job_logs.return_value = logs_payload

        result = runner.invoke(app, ["project", "job_logs", "job-1"])

    assert result.exit_code == 0
    assert "Job ID: job-1" in result.output
    assert "Status: failed" in result.output
    assert "Error: Protocol failed" in result.output
    assert "12:00:03 error: Boom" in result.output
    assert "Use 'securegenomics project logs proj-1' for enhanced formatting" in result.output


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
