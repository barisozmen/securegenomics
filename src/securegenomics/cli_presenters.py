"""Presentation helpers for the SecureGenomics CLI."""

import json
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any


PROJECT_STATUS_COLORS = {
    "pending": "yellow",
    "running": "blue",
    "completed": "green",
    "failed": "red",
    "no_jobs": "dim",
}

JOB_STATUS_COLORS = {
    "pending": "yellow",
    "running": "blue",
    "completed": "green",
    "failed": "red",
}

STEP_ICONS = {
    "start": "🚀",
    "validate": "✅",
    "load": "📥",
    "compute": "⚡",
    "finalize": "🏁",
    "error": "❌",
    "stop": "⏹️",
}

STEP_COLORS = {
    "start": "cyan",
    "validate": "green",
    "load": "blue",
    "compute": "magenta",
    "finalize": "green",
    "error": "red",
    "stop": "yellow",
}


def print_json(console: Any, payload: Mapping[str, Any], *, indent: int | None = None) -> None:
    console.print(json.dumps(payload, indent=indent, default=str))


def print_json_success(console: Any, **payload: Any) -> None:
    print_json(console, {"success": True, **payload})


def print_json_error(
    console: Any,
    error: Exception,
    *,
    include_success: bool = True,
    indent: int | None = None,
) -> None:
    payload: dict[str, Any] = {"error": str(error)}
    if include_success:
        payload = {"success": False, **payload}
    print_json(console, payload, indent=indent)


def project_status_color(status: str) -> str:
    return PROJECT_STATUS_COLORS.get(status, "white")


def job_status_color(status: str) -> str:
    return JOB_STATUS_COLORS.get(status, "white")


def format_project_datetime(value: str) -> str:
    return _parse_utc_datetime(value).strftime("%Y-%m-%d %H:%M UTC")


def format_job_datetime(value: str) -> str:
    return _parse_utc_datetime(value).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_contributors(contributors: list[Any]) -> str:
    return ", ".join(
        contributor["email"] if isinstance(contributor, dict) else str(contributor)
        for contributor in contributors
    )


def render_project_list(console: Any, response: Any, *, detailed: bool) -> None:
    if detailed:
        if isinstance(response, dict) and "count" in response:
            _render_detailed_project_list(console, response)
        else:
            console.print("[yellow]⚠️  Detailed information unavailable, showing basic listing[/yellow]")
            _render_basic_project_list(console, response, allow_missing_status=True)
        return

    _render_basic_project_list(console, response)


def render_project_view(console: Any, project_info: Mapping[str, Any], project_id: str) -> None:
    console.print("\n[bold cyan]🧬 Project Details[/bold cyan]")
    console.print(f"   ID: [dim]{project_info['id']}[/dim]")
    console.print(f"   Protocol: [bold]{project_info['protocol_name']}[/bold]")
    console.print(f"   Created: {format_project_datetime(project_info['created_at'])}")
    _render_project_status(console, project_info)
    _render_crypto_context(console, project_info)
    _render_project_data(console, project_info)
    _render_latest_job(console, project_info)

    if project_info["protocol_description"]:
        console.print("\n[bold]Description:[/bold]")
        console.print(f"   {project_info['protocol_description']}")

    _render_project_next_steps(console, project_info, project_id)


def render_project_logs(
    console: Any,
    logs_data: Mapping[str, Any],
    project_id: str,
) -> tuple[Mapping[str, Any], int]:
    job = logs_data["job"]
    events = logs_data.get("events", [])
    error_summary = logs_data.get("error_summary") or job.get("error_summary")

    console.print("\n[bold cyan]📋 Job Logs[/bold cyan]")
    console.print(f"   Job ID: [dim]{job['id']}[/dim]")
    console.print(
        f"   Project: [bold]{job.get('protocol_name', 'unknown')}[/bold] "
        f"([dim]{job.get('project_id', project_id)}[/dim])"
    )

    status_color = job_status_color(job["status"])
    console.print(f"   Status: [{status_color}]{job['status'].title()}[/{status_color}]")

    if job.get("started_at"):
        console.print(f"   Started: {format_job_datetime(job['started_at'])}")

        if job.get("finished_at"):
            console.print(f"   Finished: {format_job_datetime(job['finished_at'])}")

    if job["status"] == "failed" and error_summary:
        console.print(f"   [red]Error: {error_summary}[/red]")
        if job.get("failure_code"):
            console.print(f"   [red]Failure code: {job['failure_code']}[/red]")

    console.print()

    if events:
        console.print(f"[bold]📝 Log Events ({len(events)} total):[/bold]")
        for event in events:
            render_log_event(console, event)
    else:
        console.print("[dim]No log events recorded yet[/dim]")

    return job, len(events)


def follow_project_logs(
    console: Any,
    *,
    fetch_logs: Callable[[], Mapping[str, Any]],
    seen: int,
) -> None:
    console.print("\n[yellow]Following logs for running job... (Press Ctrl+C to stop)[/yellow]")

    try:
        while True:
            time.sleep(3)
            updated_logs = fetch_logs()
            new_job_status = updated_logs["job"]["status"]
            new_events = updated_logs.get("events", [])

            if len(new_events) > seen:
                for event in new_events[seen:]:
                    render_log_event(console, event)
                seen = len(new_events)

            if new_job_status in ["completed", "failed"]:
                console.print(f"\n[bold]Job {new_job_status}![/bold]")
                break

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped following logs[/yellow]")


def render_project_log_next_steps(console: Any, project_id: str, status: str) -> None:
    if status == "completed":
        console.print("\n[bold]💡 Next steps:[/bold]")
        console.print(f"   View results: [blue]securegenomics project result {project_id}[/blue]")
    elif status == "failed":
        console.print("\n[bold]💡 Troubleshooting:[/bold]")
        console.print("   • Check error details in logs above")
        console.print(f"   • Verify input data: [blue]securegenomics project view {project_id}[/blue]")
        console.print("   • Contact support if issue persists")
    elif status in ["pending", "running"]:
        console.print("\n[bold]💡 Job in progress:[/bold]")
        console.print(f"   • Monitor: [blue]securegenomics project logs {project_id} --follow[/blue]")
        console.print(f"   • Stop job: [blue]securegenomics project stop {project_id}[/blue]")


def render_job_logs(console: Any, logs_data: Mapping[str, Any]) -> None:
    job = logs_data["job"]
    project_id = job.get("project_id", "unknown")
    events = logs_data.get("events", [])
    error_summary = logs_data.get("error_summary") or job.get("error_summary")

    console.print("\n[bold cyan]📋 Job Logs[/bold cyan]")
    console.print(f"   Job ID: [dim]{job['id']}[/dim]")
    console.print(f"   Status: {job['status']}")
    if job["status"] == "failed" and error_summary:
        console.print(f"   [red]Error: {error_summary}[/red]")

    if events:
        console.print(f"\n[bold]📝 Log Events ({len(events)} total):[/bold]")
        for event in events:
            render_log_event(console, event, enhanced=False)

    console.print(
        f"\n[dim]💡 Tip: Use 'securegenomics project logs {project_id}' "
        "for enhanced formatting[/dim]"
    )


def render_log_event(
    console: Any,
    event: Mapping[str, Any],
    *,
    enhanced: bool = True,
) -> None:
    occurred = event.get("occurred_at") or event.get("timestamp")
    time_str = _format_event_time(occurred)
    step = event.get("step") or event.get("event_type") or ""

    if not enhanced:
        console.print(f"   📌 {time_str} [bold]{step}[/bold]: {event.get('message', '')}")
        return

    relative_str = _format_relative_time(
        event.get("relative_seconds", event.get("relative_time_seconds"))
    )
    icon = STEP_ICONS.get(step, "📌")
    step_color = STEP_COLORS.get(step, "white")
    console.print(
        f"   {icon} [{step_color}]{time_str}{relative_str}[/{step_color}] "
        f"[bold]{step}[/bold]: {event.get('message', '')}"
    )


def _render_detailed_project_list(console: Any, response: Mapping[str, Any]) -> None:
    if response["count"] == 0:
        console.print("No projects found", style="yellow")
        return

    projects = response["projects"]
    console.print(f"\n[bold]Your Projects ({response['count']} total):[/bold]")

    for project in projects:
        console.print(f"\n[bold cyan]🧬 {project['protocol_name']}[/bold cyan]")
        console.print(f"   ID: [dim]{project['id']}[/dim]")
        console.print(f"   Created: {format_project_datetime(project['created_at'])}")
        _render_project_status(console, project)
        _render_crypto_context(console, project)
        _render_project_data(console, project)
        _render_latest_job(console, project)
        _render_project_description_summary(console, project)

    _render_project_summary(console, response["count"], projects)


def _render_basic_project_list(
    console: Any,
    projects: list[Mapping[str, Any]],
    *,
    allow_missing_status: bool = False,
) -> None:
    if not projects:
        console.print("No projects found", style="yellow")
        return

    console.print("\n[bold]Your Projects:[/bold]")
    for project in projects:
        status = project.get("status", "unknown") if allow_missing_status else project["status"]
        console.print(f"• {project['id']}: {project['protocol_name']} ({status})")


def _render_project_status(console: Any, project: Mapping[str, Any]) -> None:
    status = project["job_status"]
    status_color = project_status_color(status)
    console.print(
        f"   Status: [{status_color}]{status.replace('_', ' ').title()}[/{status_color}]"
    )


def _render_crypto_context(console: Any, project: Mapping[str, Any]) -> None:
    context_status = "✅ Ready" if project["has_context"] else "❌ Not generated"
    console.print(f"   Crypto Context: {context_status}")


def _render_project_data(console: Any, project: Mapping[str, Any]) -> None:
    if project["vcf_count"] > 0:
        contributor_text = (
            f"{project['contributor_count']} contributor(s)"
            if project["contributor_count"] > 1
            else "1 contributor"
        )
        console.print(f"   Data: {project['vcf_count']} VCF file(s) from {contributor_text}")

        if project["contributors"]:
            console.print(f"   Contributors: {format_contributors(project.get('contributors', []))}")
    else:
        console.print("   Data: [dim]No VCF files uploaded yet[/dim]")


def _render_latest_job(console: Any, project: Mapping[str, Any]) -> None:
    if project["latest_job_id"]:
        if project["latest_job_finished"]:
            finished_str = format_project_datetime(project["latest_job_finished"])
            console.print(f"   Latest Job: {project['latest_job_id']} (finished: {finished_str})")
        elif project["latest_job_created"]:
            created_str = format_project_datetime(project["latest_job_created"])
            console.print(f"   Latest Job: {project['latest_job_id']} (started: {created_str})")


def _render_project_description_summary(console: Any, project: Mapping[str, Any]) -> None:
    if project["protocol_description"]:
        description = project["protocol_description"]
        suffix = "..." if len(description) > 100 else ""
        console.print(f"   Description: [dim]{description[:100]}{suffix}[/dim]")


def _render_project_summary(
    console: Any,
    project_count: int,
    projects: list[Mapping[str, Any]],
) -> None:
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"• Total projects: {project_count}")
    ready_projects = sum(1 for project in projects if project["has_context"])
    console.print(f"• Ready for use: {ready_projects}")
    active_projects = sum(
        1 for project in projects if project["job_status"] in ["pending", "running"]
    )
    if active_projects > 0:
        console.print(f"• Active jobs: {active_projects}")


def _render_project_next_steps(
    console: Any,
    project_info: Mapping[str, Any],
    project_id: str,
) -> None:
    console.print("\n[bold]Next Steps:[/bold]")
    if not project_info["has_context"]:
        console.print(
            f"   💡 Generate crypto context: "
            f"[blue]securegenomics crypto_context generate {project_id}[/blue]"
        )
    elif project_info["vcf_count"] == 0:
        console.print(
            f"   💡 Upload VCF data: "
            f"[blue]securegenomics data encode_encrypt_upload {project_id} <vcf-file>[/blue]"
        )
    elif project_info["job_status"] == "no_jobs":
        console.print(f"   💡 Start computation: [blue]securegenomics project run {project_id}[/blue]")
    elif project_info["job_status"] == "completed":
        console.print(f"   💡 View results: [blue]securegenomics project result {project_id}[/blue]")
    elif project_info["job_status"] in ["pending", "running"]:
        console.print(
            f"   💡 Check status: [blue]securegenomics project job_status {project_id}[/blue]"
        )


def _format_event_time(value: str | None) -> str:
    if not value:
        return ""
    return _parse_utc_datetime(value).strftime("%H:%M:%S")


def _format_relative_time(value: float | int | None) -> str:
    if value is None:
        return ""
    if value >= 60:
        return f" (+{value//60:.0f}m{value%60:02.0f}s)"
    return f" (+{value:.1f}s)"


def _parse_utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
