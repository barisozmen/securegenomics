"""
SecureGenomics CLI - Main command-line interface.

This module provides the main entry point and command structure for the CLI.
It organizes all operations into logical command groups.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.traceback import install

from securegenomics import __version__
from securegenomics.auth import AuthManager
from securegenomics.protocol import ProtocolManager
from securegenomics.project import ProjectManager
from securegenomics.data import DataManager
from securegenomics.crypto_context import CryptoContextManager
from securegenomics.local import LocalAnalyzer
from securegenomics.config import ConfigManager
from securegenomics.cli_presenters import (
    follow_project_logs,
    print_json,
    print_json_error,
    print_json_success,
    render_job_logs,
    render_project_list,
    render_project_log_next_steps,
    render_project_logs,
    render_project_view,
)

# Install rich traceback handler for better error display
install(show_locals=True)

# Initialize console for rich output
console = Console()


def _build_manager(manager_cls):
    """Instantiate a manager, turning an insecure-config error into a clean exit.

    Manager ``__init__``s resolve the server URL via
    ``ConfigManager.get_server_url``, which calls ``enforce_https`` and raises
    ``ValueError`` for a non-loopback ``http`` server_url. Catch it at the
    command boundary so the user sees the reason instead of a raw traceback.
    Fail closed: abort the command; never fall back to an insecure connection.
    """
    try:
        return manager_cls()
    except ValueError as e:
        console.print(f"❌ {e}", style="red")
        raise typer.Exit(1)


# Main CLI app
app = typer.Typer(
    name="securegenomics",
    help="SecureGenomics CLI - Secure genomic computation platform",
    add_completion=False,
    rich_markup_mode="rich",
)

# Command groups
auth_app = typer.Typer(help="Authentication commands")
protocol_app = typer.Typer(help="Protocol management commands")
project_app = typer.Typer(help="Project management commands")
crypto_context_app = typer.Typer(help="Crypto context commands (generate, upload)")
data_app = typer.Typer(help="Data processing commands (encode, encrypt, upload)")
local_app = typer.Typer(help="Local analysis commands")
system_app = typer.Typer(help="System commands")

app.add_typer(auth_app, name="auth")
app.add_typer(protocol_app, name="protocol")
app.add_typer(project_app, name="project")
app.add_typer(crypto_context_app, name="crypto_context")
app.add_typer(data_app, name="data")
app.add_typer(local_app, name="local")
app.add_typer(system_app, name="system")

# Global options
@app.callback(invoke_without_command=True)
def cli_callback(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output in JSON format"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Verbose output"
    ),
) -> None:
    """
    SecureGenomics CLI - The single source of truth for secure genomic computation.
    
    Two analysis modes:
    • Local-only: Run analysis locally without encryption or server
    • Aggregated: Secure multi-party computation across encrypted datasets
    """
    if version:
        console.print(f"SecureGenomics CLI version {__version__}")
        raise typer.Exit()
    
    # Set global output format environment variables for other modules
    if json_output:
        os.environ["SECUREGENOMICS_JSON"] = "1"
    if quiet:
        os.environ["SECUREGENOMICS_QUIET"] = "1"
    if verbose:
        os.environ["SECUREGENOMICS_VERBOSE"] = "1"


def big_announcement(text) -> None:
    print('\n' + '='*60)
    try:
        import pyfiglet
    except ImportError:
        pyfiglet = None

    if isinstance(text, str):
        print(pyfiglet.figlet_format(text, font='slant') if pyfiglet else text)
    else:
        for line in text:
            print(pyfiglet.figlet_format(line, font='slant') if pyfiglet else line)
    print('='*60 + '\n')


# ============================================================================
# AUTH COMMANDS
# ============================================================================

@auth_app.command("login")
def auth_login(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address (optional, will prompt if not provided)"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (optional, will prompt securely if not provided)"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use interactive mode (default: true)"),
) -> None:
    """
    Login to SecureGenomics server.
    
    Interactive mode (default): Prompts for credentials securely
    Non-interactive mode: Requires --email and --password options
    """
    try:
        auth_manager = _build_manager(AuthManager)
        
        # Try environment variables first
        env_email = os.getenv("SECUREGENOMICS_EMAIL")
        env_password = os.getenv("SECUREGENOMICS_PASSWORD")
        
        # Use provided args or fall back to environment variables
        email = email or env_email
        password = password or env_password
        
        # Interactive mode - elegant UX
        if interactive and not (email and password):
            success = auth_manager.interactive_login()
        # Non-interactive mode - for scripts/CI
        elif email and password:
            success = auth_manager.login(email, password)
        # Hybrid mode - some params provided
        elif email and not password:
            from getpass import getpass
            password = getpass("Password: ")
            success = auth_manager.login(email, password)
        else:
            console.print("❌ In non-interactive mode, provide credentials via:", style="red")
            console.print("   • --email and --password options")
            console.print("   • SECUREGENOMICS_EMAIL and SECUREGENOMICS_PASSWORD environment variables")
            console.print("   • Use interactive mode (default)")
            raise typer.Exit(1)
        
        if success:
            console.print("✅ Successfully logged in", style="green")
        else:
            console.print("❌ Login failed", style="red")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ Login error: {e}", style="red")
        raise typer.Exit(1)


@auth_app.command("register")
def auth_register(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address (optional, will prompt if not provided)"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (optional, will prompt securely if not provided)"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use interactive mode (default: true)"),
) -> None:
    """
    Register new SecureGenomics account.
    
    Interactive mode (default): Prompts for credentials securely with confirmation
    Non-interactive mode: Requires --email and --password options
    """
    try:
        auth_manager = _build_manager(AuthManager)
        
        # Try environment variables first
        env_email = os.getenv("SECUREGENOMICS_EMAIL")
        env_password = os.getenv("SECUREGENOMICS_PASSWORD")
        
        # Use provided args or fall back to environment variables
        email = email or env_email
        password = password or env_password
        
        # Interactive mode - elegant UX with password confirmation
        if interactive and not (email and password):
            success = auth_manager.interactive_register()
        # Non-interactive mode - for scripts/CI
        elif email and password:
            success = auth_manager.register(email, password)
        # Hybrid mode - some params provided
        elif email and not password:
            from getpass import getpass
            password = getpass("Choose password: ")
            confirm_password = getpass("Confirm password: ")
            if password != confirm_password:
                console.print("❌ Passwords don't match", style="red")
                raise typer.Exit(1)
            success = auth_manager.register(email, password)
        else:
            console.print("❌ In non-interactive mode, provide credentials via:", style="red")
            console.print("   • --email and --password options")
            console.print("   • SECUREGENOMICS_EMAIL and SECUREGENOMICS_PASSWORD environment variables")
            console.print("   • Use interactive mode (default)")
            raise typer.Exit(1)
        
        if success:
            console.print("✅ Successfully registered and logged in", style="green")
        else:
            console.print("❌ Registration failed", style="red")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ Registration error: {e}", style="red")
        raise typer.Exit(1)


@auth_app.command("logout")
def auth_logout() -> None:
    """Logout from SecureGenomics."""
    try:
        auth_manager = _build_manager(AuthManager)
        auth_manager.logout()
        console.print("✅ Successfully logged out", style="green")
    except Exception as e:
        console.print(f"❌ Logout error: {e}", style="red")
        raise typer.Exit(1)


@auth_app.command("whoami")
def auth_whoami() -> None:
    """Show current user information."""
    try:
        auth_manager = _build_manager(AuthManager)
        user_info = auth_manager.whoami()
        if user_info:
            console.print(f"Logged in as: {user_info['email']}", style="green")
        else:
            console.print("Not logged in", style="yellow")
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@auth_app.command("quick")
def auth_quick() -> None:
    """Quick login using stored credentials or interactive prompt."""
    try:
        auth_manager = _build_manager(AuthManager)
        
        # Check if already authenticated
        if auth_manager.is_authenticated():
            user_info = auth_manager.whoami()
            email = user_info.get("email", "unknown") if user_info else "unknown"
            console.print(f"✅ Already logged in as {email}", style="green")
            return
        
        # Try interactive login
        success = auth_manager.interactive_login()
        if success:
            console.print("✅ Successfully logged in", style="green")
        else:
            console.print("❌ Login failed", style="red")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@auth_app.command("delete_profile")
def auth_delete_profile() -> None:
    """Account deletion (not available from the CLI yet)."""
    # The Gencrypt API exposes no account-deletion endpoint. Degrade gracefully
    # (delete_profile prints the guidance and returns False) rather than running
    # a destructive confirmation flow that can't complete.
    _build_manager(AuthManager).delete_profile()


# ============================================================================
# PROTOCOL COMMANDS
# ============================================================================

@protocol_app.command("list")
def protocol_list(
    json_output: bool = typer.Option(False, "--json", help="Output protocols as JSON")
) -> None:
    """List available protocols from GitHub."""
    try:
        protocol_manager = _build_manager(ProtocolManager)
        protocols = protocol_manager.list_protocols()
        
        if json_output:
            # Convert protocols to dict format for JSON serialization
            protocols_data = []
            for protocol in protocols:
                protocols_data.append({
                    "name": protocol.name,
                    "description": protocol.description,
                    "github_url": protocol.github_url,
                    "commit_hash": protocol.commit_hash,
                    "version": protocol.version,
                    "analysis_type": protocol.analysis_type,
                    "local_supported": protocol.local_supported,
                    "aggregated_supported": protocol.aggregated_supported
                })
            
            print_json_success(console, protocols=protocols_data, count=len(protocols_data))
        else:
            # Original table output
            if not protocols:
                console.print("No protocols found", style="yellow")
                return
            
            console.print("\n[bold blue]Available Protocols:[/bold blue]")
            for i, protocol in enumerate(protocols, 1):
                supports = []
                if protocol.local_supported:
                    supports.append("Local")
                if protocol.aggregated_supported:
                    supports.append("Aggregated")
                
                console.print(f"{i:2}. [bold green]{protocol.name}[/bold green]")
                console.print(f"    {protocol.description}")
                console.print(f"    Supports: {', '.join(supports)}")
                if protocol.analysis_type:
                    console.print(f"    Type: {protocol.analysis_type}")
                console.print()
                
    except Exception as e:
        if json_output:
            print_json_error(console, e)
        else:
            console.print(f"❌ Error listing protocols: {e}", style="red")
        raise typer.Exit(1)


@protocol_app.command("fetch")
def protocol_fetch(
    protocol_name: str = typer.Argument(..., help="Protocol name to fetch"),
) -> None:
    """Fetch (clone) protocol from GitHub."""
    try:
        protocol_manager = _build_manager(ProtocolManager)
        protocol = protocol_manager.fetch(protocol_name)
        console.print(f"✅ Successfully fetched protocol: {protocol.name}", style="green")
    except Exception as e:
        console.print(f"❌ Error fetching protocol: {e}", style="red")
        raise typer.Exit(1)


@protocol_app.command("verify")
def protocol_verify(
    protocol_name: str = typer.Argument(..., help="Protocol name to verify"),
) -> None:
    """Verify protocol integrity."""
    try:
        protocol_manager = _build_manager(ProtocolManager)
        is_valid = protocol_manager.verify(protocol_name)
        if is_valid:
            console.print(f"✅ Protocol {protocol_name} is valid", style="green")
        else:
            console.print(f"❌ Protocol {protocol_name} verification failed", style="red")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ Error verifying protocol: {e}", style="red")
        raise typer.Exit(1)


@protocol_app.command("locals")
def protocol_locals() -> None:
    """List locally cached protocols with detailed information."""
    try:
        protocol_manager = _build_manager(ProtocolManager)
        local_protocols = protocol_manager.list_local_protocols()
        
        if not local_protocols:
            console.print("No protocols cached locally", style="yellow")
            console.print("💡 Use 'securegenomics protocol fetch <protocol-name>' to download protocols", style="blue")
            return
        
        console.print(f"\n[bold]Locally Cached Protocols ({len(local_protocols)} total):[/bold]")
        
        for protocol in local_protocols:
            # Protocol header with validation status
            status_indicator = "✅" if protocol["is_valid"] else "❌"
            console.print(f"\n{status_indicator} [bold cyan]{protocol['name']}[/bold cyan]")
            
            # Basic information
            console.print(f"   Description: {protocol['description']}")
            console.print(f"   Version: {protocol['version']}")
            console.print(f"   Analysis Type: {protocol['analysis_type']}")
            
            # Supported modes
            modes = protocol['modes']
            if modes:
                mode_indicators = []
                if protocol['local_supported']:
                    mode_indicators.append("[green]Local[/green]")
                if protocol['aggregated_supported']:
                    mode_indicators.append("[blue]Aggregated[/blue]")
                console.print(f"   Modes: {' • '.join(mode_indicators)}")
            else:
                console.print("   Modes: [dim]Unknown[/dim]")
            
            # Git information
            if protocol['commit_hash'] != "unknown":
                console.print(f"   Commit: {protocol['commit_hash']}")
                if protocol['commit_date'] != "unknown":
                    console.print(f"   Date: {protocol['commit_date']}")
            
            # Validation errors if any
            if not protocol["is_valid"] and protocol["validation_errors"]:
                console.print("   [red]Validation Errors:[/red]")
                for error in protocol["validation_errors"]:
                    console.print(f"     • {error}")
            
            # Cache location
            console.print(f"   [dim]Cache: {protocol['cache_path']}[/dim]")
        
        # Summary
        valid_count = sum(1 for p in local_protocols if p["is_valid"])
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"• Total cached: {len(local_protocols)}")
        console.print(f"• Valid protocols: {valid_count}")
        if valid_count < len(local_protocols):
            invalid_count = len(local_protocols) - valid_count
            console.print(f"• Invalid protocols: {invalid_count}")
            console.print("💡 Use 'securegenomics protocol refresh <protocol-name>' to fix invalid protocols", style="blue")
        
    except Exception as e:
        console.print(f"❌ Error listing local protocols: {e}", style="red")
        raise typer.Exit(1)


@protocol_app.command("remove_local")
def protocol_remove_local(
    protocol_name: str = typer.Argument(..., help="Protocol name to remove from local cache"),
) -> None:
    """Remove a locally cached protocol."""
    try:
        from rich.prompt import Confirm
        
        protocol_manager = _build_manager(ProtocolManager)
        
        # Show warning and confirmation
        console.print(f"\n[bold yellow]⚠️  WARNING: This will remove the local cache of protocol '{protocol_name}'[/bold yellow]")
        console.print("You will need to fetch it again to use it.")
        
        confirm = Confirm.ask(f"Are you sure you want to remove protocol '{protocol_name}' from local cache?", default=False)
        if not confirm:
            console.print("Protocol removal cancelled")
            return
        
        success = protocol_manager.remove_local_protocol(protocol_name)
        if success:
            console.print(f"💡 To re-download: 'securegenomics protocol fetch {protocol_name}'", style="blue")
    except Exception as e:
        console.print(f"❌ Error removing local protocol: {e}", style="red")
        raise typer.Exit(1)


@protocol_app.command("refresh")
def protocol_refresh(
    protocol_name: str = typer.Argument(..., help="Protocol name to refresh"),
) -> None:
    """Refresh a locally cached protocol (remove and re-download)."""
    try:
        protocol_manager = _build_manager(ProtocolManager)
        protocol_info = protocol_manager.refresh_protocol(protocol_name)
        
        console.print(f"✅ Protocol {protocol_name} refreshed successfully", style="green")
        console.print(f"   Version: {protocol_info.version or 'unknown'}")
        console.print(f"   Description: {protocol_info.description}")
        console.print(f"💡 Protocol is now ready for use", style="blue")
        
    except Exception as e:
        console.print(f"❌ Error refreshing protocol: {e}", style="red")
        raise typer.Exit(1)


# ============================================================================
# PROJECT COMMANDS  
# ============================================================================

@project_app.command("create")
def project_create(
    protocol_name: Optional[str] = typer.Option(None, "--protocol", "-p", help="Protocol name (non-interactive mode)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Project description (optional)"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use interactive mode (default: true)"),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON")
) -> None:
    """Create new aggregated analysis project.
    
    Interactive mode (default): Guides you through protocol selection
    Non-interactive mode: Requires --protocol option
    
    After creating the project, automatically generates and uploads crypto context.
    """
    try:
        project_manager = _build_manager(ProjectManager)
        
        if not interactive:
            # Non-interactive mode - requires protocol name
            if not protocol_name:
                console.print("❌ Non-interactive mode requires --protocol option", style="red")
                console.print("💡 Use 'securegenomics protocol list' to see available protocols", style="blue")
                raise typer.Exit(1)
            
            # Create project directly
            project_id = project_manager.create(protocol_name)
            
            if not json_output:
                console.print(f"✅ Created project: {project_id}", style="green")
                console.print(f"Protocol: {protocol_name}")
                if description:
                    console.print(f"Description: {description}")
        else:
            # Interactive mode - original behavior
            project_id = project_manager.interactive_create()
            
            if not json_output:
                console.print(f"✅ Created project: {project_id}", style="green")
        
        # Automatically generate and upload crypto context after project creation
        if not json_output:
            console.print("🔄 Generating and uploading crypto context...", style="blue")
        
        crypto_context_manager = _build_manager(CryptoContextManager)
        crypto_context_manager.generate_upload_crypto_context(project_id)
        
        if json_output:
            print_json_success(
                console,
                project_id=project_id,
                protocol_name=protocol_name if not interactive else None,
                description=description or None,
                crypto_context_ready=True,
            )
        else:
            console.print(f"✅ Project {project_id} is ready for data upload!", style="green")
            console.print(f"💡 Next step: Upload VCF data with 'securegenomics data encode_encrypt_upload {project_id} <vcf-file>'", style="blue")
                
    except Exception as e:
        if json_output:
            print_json_error(console, e)
        else:
            console.print(f"❌ Error creating project: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("list")
def project_list(
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed project information"),
) -> None:
    """List your projects."""
    try:
        project_manager = _build_manager(ProjectManager)
        response = project_manager.list_projects(detailed=detailed)
        render_project_list(console, response, detailed=detailed)
    except Exception as e:
        console.print(f"❌ Error listing projects: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("view")
def project_view(
    project_id: str = typer.Argument(..., help="Project ID to view"),
) -> None:
    """View detailed information for a specific project."""
    try:
        project_manager = _build_manager(ProjectManager)
        project_info = project_manager.view(project_id)
        render_project_view(console, project_info, project_id)
        
    except Exception as e:
        console.print(f"❌ Error viewing project: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("list_saved_results")
def project_list_saved_results(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """List all saved encrypted and decrypted results for a project."""
    try:
        project_manager = _build_manager(ProjectManager)
        saved_results = project_manager.list_saved_results(project_id)
        
        if not saved_results:
            console.print(f"No saved results found for project {project_id}")
            return
        
        console.print(f"\n[bold]Saved Results for Project {project_id}:[/bold]")
        
        from rich.table import Table
        import datetime
        
        table = Table(title=f"Saved Results ({len(saved_results)} files)")
        table.add_column("Type", style="magenta")
        table.add_column("Filename", style="cyan")
        table.add_column("Size", style="green")
        table.add_column("Created", style="yellow")
        table.add_column("Path", style="dim")
        
        for result in saved_results:
            # Format file size
            size_bytes = result["size_bytes"]
            if size_bytes > 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            elif size_bytes > 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} B"
            
            # Format creation time
            created_time = datetime.datetime.fromtimestamp(result["created_at"])
            created_str = created_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Format type with emoji
            type_display = "🔒 Encrypted" if result["type"] == "encrypted" else "🔓 Decrypted"
            
            table.add_row(
                type_display,
                result["filename"],
                size_str,
                created_str,
                result["full_path"]
            )
        
        console.print(table)
        console.print(f"\n[dim]Results directory: {project_manager._get_results_dir(project_id)}[/dim]")
        
    except Exception as e:
        console.print(f"❌ Error listing saved results: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("delete")
def project_delete(
    project_id: str = typer.Argument(..., help="Project ID to delete"),
) -> None:
    """Delete a project and all associated data."""
    try:
        from rich.prompt import Confirm
        
        console.print(f"\n[bold red]⚠️  WARNING: This will permanently delete project {project_id}![/bold red]")
        console.print("This includes:")
        console.print("• All uploaded VCF files")
        console.print("• All computation results")
        console.print("• All project metadata")
        console.print("• Local crypto context")
        console.print("• This action cannot be undone\n")
        
        confirm = Confirm.ask(f"Are you sure you want to delete project {project_id}?", default=False)
        if not confirm:
            console.print("Project deletion cancelled")
            return
        
        project_manager = _build_manager(ProjectManager)
        success = project_manager.delete(project_id)
        if success:
            console.print(f"✅ Project {project_id} deleted successfully", style="green")
        else:
            console.print(f"❌ Failed to delete project {project_id}", style="red")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ Error deleting project: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("add-member")
def project_add_member(
    project_id: str = typer.Argument(..., help="Project ID to grant access to"),
    email: str = typer.Argument(..., help="Email of the Gencrypt user to add as a member"),
) -> None:
    """Grant another Gencrypt user access to a project.

    Only the project owner can add members. New contributors must be added
    before they can upload data, download the crypto context, or run the
    protocol — the owner is the only member enrolled automatically.
    """
    try:
        project_manager = _build_manager(ProjectManager)
        member = project_manager.add_member(project_id, email)
        member_email = member.get("email", email) if isinstance(member, dict) else email
        console.print(f"✅ Added {member_email} to project {project_id}", style="green")
    except Exception as e:
        console.print(f"❌ Error adding member: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("logs")
def project_logs(
    project_id: str = typer.Argument(..., help="Project ID"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Specific job ID (defaults to latest job)"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log updates (for running jobs)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """View detailed logs for project jobs with elegant formatting."""
    try:
        project_manager = _build_manager(ProjectManager)
        
        if job_id:
            # Get logs for specific job
            logs_data = project_manager.get_job_logs(job_id)
        else:
            # Get logs for latest job of project
            logs_data = project_manager.get_project_job_logs(project_id)
        
        if json_output:
            print_json(console, logs_data, indent=2)
            return
        
        job, event_count = render_project_logs(console, logs_data, project_id)

        # Follow mode for running jobs
        if follow and job['status'] in ['pending', 'running']:
            def fetch_logs():
                if job_id:
                    return project_manager.get_job_logs(job_id)
                return project_manager.get_project_job_logs(project_id)

            follow_project_logs(console, fetch_logs=fetch_logs, seen=event_count)

        render_project_log_next_steps(console, project_id, job['status'])
        
    except Exception as e:
        if json_output:
            print_json_error(console, e, include_success=False, indent=2)
        else:
            console.print(f"❌ Error retrieving logs: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("job_logs")
def project_job_logs(
    job_id: str = typer.Argument(..., help="Job ID"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """View logs for a specific job ID."""
    try:
        project_manager = _build_manager(ProjectManager)
        logs_data = project_manager.get_job_logs(job_id)
        
        if json_output:
            print_json(console, logs_data, indent=2)
            return
        
        render_job_logs(console, logs_data)
        
    except Exception as e:
        if json_output:
            print_json_error(console, e, include_success=False, indent=2)
        else:
            console.print(f"❌ Error retrieving job logs: {e}", style="red")
        raise typer.Exit(1)


# ============================================================================
# DATA COMMANDS
# ============================================================================

@data_app.command("encode")
def data_encode(
    project_id: str = typer.Argument(..., help="Project ID"),
    vcf_file: Path = typer.Argument(..., help="VCF file to encode", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory (default: project data cache)"),
) -> None:
    """Encode VCF file using project's protocol (step 1 of 3)."""
    try:
        data_manager = _build_manager(DataManager)
        encoded_path = data_manager.encode_vcf(project_id, vcf_file, output_dir)
        console.print(f"✅ Encoded {vcf_file.name} for project {project_id}")
        console.print(f"📁 Output: {encoded_path}")
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@data_app.command("encrypt")
def data_encrypt(
    project_id: str = typer.Argument(..., help="Project ID"),
    encoded_file: Path = typer.Argument(..., help="Encoded file to encrypt", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory (default: project data cache)"),
) -> None:
    """Encrypt encoded data using project's crypto context (step 2 of 3)."""
    try:
        data_manager = _build_manager(DataManager)
        encrypted_path, stats = data_manager.encrypt_vcf(project_id, encoded_file, output_dir)
        console.print(f"✅ Encrypted {encoded_file.name} for project {project_id}")
        console.print(f"📁 Output: {encrypted_path}")
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@data_app.command("upload")
def data_upload(
    project_id: str = typer.Argument(..., help="Project ID"),
    encrypted_file: Path = typer.Argument(..., help="Encrypted file to upload", exists=True),
) -> None:
    """Upload encrypted data file to server (step 3 of 3)."""
    try:
        data_manager = _build_manager(DataManager)
        data_manager.upload_data(project_id, encrypted_file)
        console.print(f"✅ Uploaded {encrypted_file.name} to project {project_id}")
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@data_app.command("encode_encrypt_upload")
def data_encode_encrypt_upload(
    project_id: str = typer.Argument(..., help="Project ID"),
    vcf_file: Path = typer.Argument(..., help="VCF file to process", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for intermediate files (default: project data cache)"),
) -> None:
    """Complete VCF processing pipeline: encode, encrypt, and upload (combined operation)."""
    try:
        data_manager = _build_manager(DataManager)
        data_manager.encode_encrypt_upload(project_id, vcf_file, output_dir)
        console.print(f"✅ Completed full pipeline for {vcf_file.name} in project {project_id}")
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


# ============================================================================
# LOCAL COMMANDS
# ============================================================================

@local_app.command("analyze")
def local_analyze(
    protocol_name: str = typer.Option(None, "--protocol", "-p", help="Protocol name"),
    vcf_file: Path = typer.Option(None, "--vcf", "-f", help="VCF file to analyze"),
) -> None:
    """Run local analysis on VCF file."""
    try:
        analyzer = _build_manager(LocalAnalyzer)

        # Get protocol name interactively if not provided
        if protocol_name is None:
            local_protocols = analyzer.list_local_protocols()
            if not local_protocols:
                console.print("❌ No protocols available for local analysis", style="red")
                raise typer.Exit(1)
            
            console.print("\nAvailable protocols:")
            for i, protocol in enumerate(supported_protocols, 1):
                info = analyzer.get_protocol_info(protocol)
                desc = info.get('description', 'No description') if info else 'No description'
                console.print(f"{i}. {protocol} - {desc}")
            
            while True:
                choice = console.input("\nSelect protocol (enter number or name): ")
                try:
                    # Try as index first
                    if choice.isdigit() and 1 <= int(choice) <= len(supported_protocols):
                        protocol_name = supported_protocols[int(choice)-1]
                        break
                    # Try as protocol name
                    elif choice in supported_protocols:
                        protocol_name = choice
                        break
                    else:
                        console.print("Invalid selection, please try again", style="red")
                except (ValueError, IndexError):
                    console.print("Invalid selection, please try again", style="red")

        # Get VCF file interactively if not provided
        if vcf_file is None:
            while True:
                path = console.input("\nEnter path to VCF file: ")
                vcf_file = Path(path)
                if vcf_file.exists() and vcf_file.is_file():
                    break
                console.print("File not found, please try again", style="red")

        analyzer.analyze(protocol_name, vcf_file)
    except Exception as e:
        console.print(f"❌ Error running analysis: {e}", style="red")
        raise typer.Exit(1)


# ============================================================================
# SYSTEM COMMANDS
# ============================================================================

@system_app.command("status")
def system_status() -> None:
    """Check system status and connectivity.

    Connectivity is derived from the /api/profile probe (200/401 both mean the
    server is up). Gencrypt runs on Solid Queue, not Celery, and exposes no
    /api/system endpoint, so there is no worker/broker readout.
    """
    try:
        config_manager = _build_manager(ConfigManager)
        status = config_manager.get_system_status()

        console.print("\n[bold]System Status:[/bold]")
        console.print(f"CLI Version: {__version__}")
        console.print(f"Config Directory: {status['config_dir']}")
        console.print(f"Server URL: {status['server_url']}")
        console.print(f"Server Connection: {'✅' if status['server_connected'] else '❌'}")
        console.print(f"Authenticated: {'✅' if status['authenticated'] else '❌'}")
        console.print(f"Cached Protocols: {status['cached_protocols']}")

    except Exception as e:
        console.print(f"❌ Error checking status: {e}", style="red")
        raise typer.Exit(1)


@system_app.command("celery-status")
def system_celery_status() -> None:
    """Deprecated: Gencrypt runs Solid Queue, not Celery.

    Kept as a graceful no-op so existing scripts don't crash. Reports plain
    server connectivity via the /api/profile probe instead of a Celery/Redis
    readout that no longer exists.
    """
    console.print(
        "[yellow]Celery diagnostics are not applicable — Gencrypt runs Solid Queue.[/yellow]"
    )
    try:
        config_manager = _build_manager(ConfigManager)
        status = config_manager.get_system_status()
        console.print(f"Server URL: {status['server_url']}")
        console.print(f"Server Connection: {'✅' if status['server_connected'] else '❌'}")
        console.print("\n💡 Inspect jobs with:")
        console.print("   [blue]securegenomics project list --detailed[/blue]")
        console.print("   [blue]securegenomics project logs <project-id>[/blue]")
    except Exception as e:
        # Never crash — this command is informational only.
        console.print(f"[dim]Could not read connectivity: {e}[/dim]")


@system_app.command("clear-cache")
def system_clear_cache() -> None:
    """Delete the entire cache directory at ~/.securegenomics/."""
    try:
        from rich.prompt import Confirm

        config_manager = _build_manager(ConfigManager)
        cache_dir = config_manager.base_config_dir

        console.print(f"\n[bold red]⚠️  WARNING: This will permanently delete the entire cache directory![/bold red]")
        console.print(f"This includes all data stored in: [yellow]{cache_dir}[/yellow]")
        console.print("• All user configurations and authentication tokens")
        console.print("• All downloaded protocols")
        console.print("• All local crypto contexts (secret keys)")
        console.print("• All project-specific data and results")
        console.print("• This action cannot be undone and will log you out from all accounts.\n")

        confirm = Confirm.ask(f"Are you absolutely sure you want to delete the entire cache directory?", default=False)
        if not confirm:
            console.print("Cache deletion cancelled.")
            return

        config_manager.clear_base_cache()
        console.print(f"✅ Successfully cleared the cache at {cache_dir}", style="green")
        console.print("💡 You will need to log in again and re-fetch any necessary data.", style="blue")

    except Exception as e:
        console.print(f"❌ Error clearing cache: {e}", style="red")
        raise typer.Exit(1)


@system_app.command("help")
def system_help() -> None:
    """Show detailed help information."""
    console.print("""
[bold]SecureGenomics CLI Help[/bold]

[bold]Two Analysis Modes:[/bold]
• Local-only: Run analysis locally without encryption or server
• Aggregated: Secure multi-party computation across encrypted datasets

[bold]Common Workflows:[/bold]

[bold]1. Local Analysis (No server needed):[/bold]
   securegenomics protocol list
   securegenomics local analyze alzheimers-risk sample.vcf

[bold]2. Aggregated Analysis (Multi-party):[/bold]
   securegenomics auth login
   securegenomics project create                          # Interactive - choose protocol
   securegenomics project generate_upload_context <project-id>
   securegenomics data encode_encrypt_upload <project-id> data.vcf
   securegenomics project run <project-id>
   securegenomics project stop <project-id>              # Stop running job if needed
   securegenomics project job_status <project-id>        # Check job status
   securegenomics project result <project-id>
   securegenomics project clear_protocol_cache <project-id>    # Clear protocol cache
   securegenomics project refresh_protocol_cache <project-id>  # Refresh protocol cache

[bold]Configuration:[/bold]
   ~/.securegenomics/config.json   - CLI settings
   ~/.securegenomics/auth.json     - Authentication tokens
   ~/.securegenomics/protocols/    - Cached protocols
   
[bold]For more help on specific commands:[/bold]
   securegenomics <command> --help
""")


# ============================================================================
# CRYPTO CONTEXT COMMANDS
# ============================================================================

@crypto_context_app.command("generate")
def crypto_context_generate(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Generate FHE crypto context locally for project (does not upload)."""
    try:
        crypto_context_manager = _build_manager(CryptoContextManager)
        
        # Validate that crypto context generation is allowed
        console.print(f"🔍 Validating project {project_id}...")
        
        # Check if server already has public context
        if crypto_context_manager.has_server_crypto_context(project_id):
            console.print(f"❌ Project {project_id} already has a public crypto context on the server.", style="red")
            console.print("Each project can only have one crypto context for security reasons.", style="red")
            raise typer.Exit(1)
        
        # Check if local context already exists
        if crypto_context_manager.has_local_crypto_context(project_id):
            console.print(f"❌ Local crypto context already exists for project {project_id}.", style="red")
            console.print("Each project can only have one crypto context for security reasons.", style="red")
            console.print(f"💡 Use 'securegenomics crypto_context upload {project_id}' to upload existing context", style="blue")
            console.print("   or delete the local context first if you want to regenerate.", style="blue")
            raise typer.Exit(1)
        
        console.print("✅ Validation passed - generating crypto context locally", style="green")
        
        # Generate crypto context (local only, no upload)
        crypto_context_manager.generate_crypto_context(project_id)
        console.print(f"✅ Generated crypto context locally for project {project_id}", style="green")
        console.print(f"💡 Next step: Upload to server with 'securegenomics crypto_context upload {project_id}'", style="blue")
        
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit codes
        raise
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@crypto_context_app.command("upload")
def crypto_context_upload(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Upload existing local crypto context to server."""
    try:
        crypto_context_manager = _build_manager(CryptoContextManager)
        
        console.print(f"🔍 Validating project {project_id}...")
        
        # Check if server already has public context
        if crypto_context_manager.has_server_crypto_context(project_id):
            console.print(f"❌ Project {project_id} already has a public crypto context on the server.", style="red")
            console.print("Each project can only have one crypto context for security reasons.", style="red")
            raise typer.Exit(1)
        
        # Check if local context exists
        if not crypto_context_manager.has_local_crypto_context(project_id):
            console.print(f"❌ No local crypto context found for project {project_id}.", style="red")
            console.print(f"💡 Use 'securegenomics crypto_context generate {project_id}' to generate a new context", style="blue")
            raise typer.Exit(1)
        
        console.print("✅ Validation passed - uploading existing crypto context", style="green")
        
        # Upload public context to server
        try:
            crypto_context_manager.upload_crypto_context(project_id)
            console.print(f"✅ Uploaded public crypto context for project {project_id}", style="green")
        except Exception as upload_error:
            # Check if it's a duplicate context error
            if "already exists on server" in str(upload_error) or "already has a public crypto context" in str(upload_error):
                console.print(f"❌ {upload_error}", style="red")
                console.print("💡 This validation should have been caught earlier. Please try refreshing and check again.", style="blue")
                raise typer.Exit(1)
            else:
                # Re-raise other upload errors
                raise
        
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit codes
        raise
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@crypto_context_app.command("download")
def crypto_context_download(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Download public crypto context from server."""
    try:
        from securegenomics.crypto import FHEManager
        
        console.print(f"🔍 Downloading public crypto context for project {project_id}...")
        
        # Download context using FHEManager
        fhe_manager = FHEManager()
        fhe_manager.download_public_context(project_id)
        
        # Log audit event
        from securegenomics.auth import AuthManager
        auth_manager = _build_manager(AuthManager)
        # auth_manager._log_audit_event("crypto_context_download", project_id=project_id)
        
        console.print(f"💾 Context saved locally and ready for data encryption")
        console.print(f"💡 You can now encrypt VCF data with: 'securegenomics data encrypt {project_id} <encoded-file>'", style="blue")
        
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit codes
        raise
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@crypto_context_app.command("generate_upload")
def crypto_context_generate_upload(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Generate FHE crypto context for project and upload to server (combined operation)."""
    try:
        crypto_context_manager = _build_manager(CryptoContextManager)
        crypto_context_manager.generate_upload_crypto_context(project_id)
        
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit codes
        raise
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@crypto_context_app.command("delete")
def crypto_context_delete(
    project_id: str = typer.Argument(..., help="Project ID"),
    local: bool = typer.Option(False, "--local", help="Delete local crypto context"),
    server: bool = typer.Option(False, "--server", help="Delete server crypto context"),
) -> None:
    """Delete crypto context from local storage or server."""
    try:
        # Validate that exactly one option is provided
        if not local and not server:
            console.print("❌ You must specify either --local or --server", style="red")
            console.print("Usage examples:", style="blue")
            console.print(f"  securegenomics crypto_context delete --local {project_id}")
            console.print(f"  securegenomics crypto_context delete --server {project_id}")
            raise typer.Exit(1)
        
        if local and server:
            console.print("❌ Cannot specify both --local and --server. Choose one.", style="red")
            raise typer.Exit(1)
        
        crypto_context_manager = _build_manager(CryptoContextManager)
        
        if local:
            # Delete local crypto context
            console.print(f"🗑️  Deleting local crypto context for project {project_id}...")
            
            # Check if local context exists
            if not crypto_context_manager.has_local_crypto_context(project_id):
                console.print(f"❌ No local crypto context found for project {project_id}", style="red")
                raise typer.Exit(1)
            
            # Confirmation prompt
            from rich.prompt import Confirm
            console.print("\n[bold red]⚠️  WARNING: This will delete your local crypto context![/bold red]")
            console.print("• You will lose the ability to decrypt results for this project")
            console.print("• You cannot regenerate the same context - each context is unique")
            console.print("• The server crypto context will remain unaffected")
            console.print("• This action cannot be undone\n")
            
            confirm = Confirm.ask(f"Are you sure you want to delete the local crypto context for project {project_id}?", default=False)
            if not confirm:
                console.print("Local crypto context deletion cancelled")
                return
            
            # Delete local context
            success = crypto_context_manager.delete_local_crypto_context(project_id)
            if success:
                console.print(f"✅ Local crypto context deleted for project {project_id}", style="green")
                console.print("⚠️  You can no longer decrypt results for this project locally", style="yellow")
            else:
                console.print(f"❌ Failed to delete local crypto context for project {project_id}", style="red")
                raise typer.Exit(1)
        
        elif server:
            # Delete server crypto context  
            console.print(f"🗑️  Deleting server crypto context for project {project_id}...")
            
            # Check if server context exists
            if not crypto_context_manager.has_server_crypto_context(project_id):
                console.print(f"❌ No server crypto context found for project {project_id}", style="red")
                raise typer.Exit(1)
            
            # Confirmation prompt
            from rich.prompt import Confirm
            console.print("\n[bold red]⚠️  WARNING: This will delete the server crypto context![/bold red]")
            console.print("• Other participants will lose the ability to encrypt data for this project")
            console.print("• The project will no longer accept new encrypted data")
            console.print("• Your local crypto context will remain unaffected")
            console.print("• You cannot upload the same context again - each context is unique")
            console.print("• This action cannot be undone\n")
            
            confirm = Confirm.ask(f"Are you sure you want to delete the server crypto context for project {project_id}?", default=False)
            if not confirm:
                console.print("Server crypto context deletion cancelled")
                return
            
            # Delete server context
            success = crypto_context_manager.delete_server_crypto_context(project_id)
            if success:
                console.print(f"✅ Server crypto context deleted for project {project_id}", style="green")
                console.print("⚠️  The project can no longer accept new encrypted data", style="yellow")
            else:
                console.print(f"❌ Failed to delete server crypto context for project {project_id}", style="red")
                raise typer.Exit(1)
        
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit codes
        raise
    except Exception as e:
        error_msg = _sanitize_error_message(str(e))
        console.print(f"❌ Error: {error_msg}", style="red")
        raise typer.Exit(1)


@project_app.command("run")
def project_run(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Start computation for project."""
    try:
        project_manager = _build_manager(ProjectManager)
        job_id = project_manager.run(project_id)
        console.print(f"✅ Started computation for project {project_id}", style="green")
        console.print(f"Job ID: {job_id}")
    except Exception as e:
        console.print(f"❌ Error starting computation: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("stop")
def project_stop(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Stop running computation for project (not yet supported by the server)."""
    # The Gencrypt API has no run-cancellation endpoint yet. Degrade gracefully
    # instead of crashing.
    console.print("[yellow]Stopping a run isn't supported yet.[/yellow]")


@project_app.command("job_status")
def project_job_status(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Check job status for project."""
    try:
        project_manager = _build_manager(ProjectManager)
        status = project_manager.get_job_status(project_id)
        console.print(f"Project {project_id} status: {status['status']}")
        if status.get('events'):
            console.print("\nJob Events:")
            for event in status['events']:
                occurred = event.get('occurred_at') or event.get('timestamp', '')
                step = event.get('step') or event.get('event_type', '')
                console.print(f"• {occurred}: {step} - {event.get('message', '')}")
    except Exception as e:
        console.print(f"❌ Error checking status: {e}", style="red")
        raise typer.Exit(1)


@project_app.command("result")
def project_result(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Get results for completed project."""
    try:
        project_manager = _build_manager(ProjectManager)
        results = project_manager.get_result(project_id)
        console.print(f"✅ Results for project {project_id}:", style="green")
        console.print(results)
    except Exception as e:
        console.print(f"❌ Error getting results: {e}", style="red")
        raise typer.Exit(1)


# ============================================================================
# COMMAND ALIASES (for convenience)
# ============================================================================

# Auth aliases
@app.command("login")
def login_alias(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address (optional, will prompt if not provided)"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (optional, will prompt securely if not provided)"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use interactive mode (default: true)"),
) -> None:
    """Login to SecureGenomics server (alias for 'auth login')."""
    auth_login(email, password, interactive)


@app.command("logout")
def logout_alias() -> None:
    """Logout from SecureGenomics (alias for 'auth logout')."""
    auth_logout()


@app.command("whoami")
def whoami_alias() -> None:
    """Show current user information (alias for 'auth whoami')."""
    auth_whoami()


@app.command("register")
def register_alias(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address (optional, will prompt if not provided)"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (optional, will prompt securely if not provided)"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use interactive mode (default: true)"),
) -> None:
    """Register new SecureGenomics account (alias for 'auth register')."""
    auth_register(email, password, interactive)


@app.command("quick")
def quick_alias() -> None:
    """Quick login (alias for 'auth quick')."""
    auth_quick()


# Crypto context aliases
@app.command("keygen")
def keygen_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Generate FHE crypto context for project (alias for 'crypto_context generate')."""
    crypto_context_generate(project_id)


@app.command("keyupload")
def keyupload_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Upload crypto context to server (alias for 'crypto_context upload')."""
    crypto_context_upload(project_id)


@app.command("keygen_upload")
def keygen_upload_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Generate and upload crypto context (alias for 'crypto_context generate_upload')."""
    crypto_context_generate_upload(project_id)


@app.command("keydownload")
def keydownload_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Download crypto context from server (alias for 'crypto_context download')."""
    crypto_context_download(project_id)


@app.command("keydelete")
def keydelete_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
    local: bool = typer.Option(False, "--local", help="Delete local crypto context"),
    server: bool = typer.Option(False, "--server", help="Delete server crypto context"),
) -> None:
    """Delete crypto context (alias for 'crypto_context delete')."""
    crypto_context_delete(project_id, local, server)


# Project aliases
@app.command("create")
def create_alias(
    protocol_name: Optional[str] = typer.Option(None, "--protocol", "-p", help="Protocol name (non-interactive mode)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Project description (optional)"),
    interactive: bool = typer.Option(True, "--interactive/--non-interactive", help="Use interactive mode (default: true)"),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON")
) -> None:
    """Create new project (alias for 'project create')."""
    project_create(protocol_name, description, interactive, json_output)
    if not json_output:
        big_announcement("Project Created")


@app.command("list")
def list_alias(
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed project information"),
) -> None:
    """List your projects (alias for 'project list')."""
    project_list(detailed)


@app.command("view")
def view_alias(
    project_id: str = typer.Argument(..., help="Project ID to view"),
) -> None:
    """View project details (alias for 'project view')."""
    project_view(project_id)


@app.command("run")
def run_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Start computation for project (alias for 'project run')."""
    project_run(project_id)


@app.command("stop")
def stop_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Stop computation for project (alias for 'project stop')."""
    project_stop(project_id)


@app.command("status")
def status_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Check job status for project (alias for 'project job_status')."""
    project_job_status(project_id)


@app.command("result")
def result_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Get results for completed project (alias for 'project result')."""
    project_result(project_id)


@app.command("delete")
def delete_alias(
    project_id: str = typer.Argument(..., help="Project ID to delete"),
) -> None:
    """Delete a project (alias for 'project delete')."""
    project_delete(project_id)


@app.command("job_status")
def job_status_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
) -> None:
    """Check job status for project (alias for 'project job_status')."""
    project_job_status(project_id)


# Data aliases
@app.command("upload")
def upload_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
    vcf_file: Path = typer.Argument(..., help="VCF file to process", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for intermediate files (default: project data cache)"),
) -> None:
    """Complete VCF upload pipeline (alias for 'data encode_encrypt_upload')."""
    data_encode_encrypt_upload(project_id, vcf_file, output_dir)
    big_announcement(["Genome Encrypted", "and Uploaded"])


@app.command("encode_encrypt_upload")
def encode_encrypt_upload_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
    vcf_file: Path = typer.Argument(..., help="VCF file to process", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for intermediate files (default: project data cache)"),
) -> None:
    """Complete VCF processing pipeline (alias for 'data encode_encrypt_upload')."""
    data_encode_encrypt_upload(project_id, vcf_file, output_dir)


@app.command("encode")
def encode_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
    vcf_file: Path = typer.Argument(..., help="VCF file to encode", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory (default: project data cache)"),
) -> None:
    """Encode VCF file (alias for 'data encode')."""
    data_encode(project_id, vcf_file, output_dir)


@app.command("encrypt")
def encrypt_alias(
    project_id: str = typer.Argument(..., help="Project ID"),
    encoded_file: Path = typer.Argument(..., help="Encoded file to encrypt", exists=True),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory (default: project data cache)"),
) -> None:
    """Encrypt encoded data (alias for 'data encrypt')."""
    data_encrypt(project_id, encoded_file, output_dir)


# Protocol aliases
@app.command("protocols")
def protocols_alias(
    json_output: bool = typer.Option(False, "--json", help="Output protocols as JSON")
) -> None:
    """List available protocols (alias for 'protocol list')."""
    protocol_list(json_output)


@app.command("fetch")
def fetch_alias(
    protocol_name: str = typer.Argument(..., help="Protocol name to fetch"),
) -> None:
    """Fetch protocol from GitHub (alias for 'protocol fetch')."""
    protocol_fetch(protocol_name)


@app.command("verify")
def verify_alias(
    protocol_name: str = typer.Argument(..., help="Protocol name to verify"),
) -> None:
    """Verify protocol integrity (alias for 'protocol verify')."""
    protocol_verify(protocol_name)


# Local analysis alias
@app.command("analyze")
def analyze_alias(
    protocol_name: str = typer.Option(None, "--protocol", "-p", help="Protocol name"),
    vcf_file: Path = typer.Option(None, "--vcf-file", "-f", help="VCF file to analyze"),
) -> None:
    """Run local analysis on VCF file (alias for 'local analyze')."""
    local_analyze(protocol_name, vcf_file)


# Entry point
def _sanitize_error_message(error_msg: str) -> str:
    """Sanitize error message to prevent Rich markup errors with binary data."""
    # Convert to string if it's bytes
    if isinstance(error_msg, bytes):
        try:
            error_msg = error_msg.decode('utf-8', errors='replace')
        except:
            error_msg = repr(error_msg)
    
    # Replace non-printable characters that could confuse Rich markup
    import re
    # Replace any character that's not printable ASCII, keeping basic punctuation
    sanitized = re.sub(r'[^\x20-\x7E\n\r\t]', '?', str(error_msg))
    
    # Escape Rich markup characters to prevent parsing issues
    sanitized = sanitized.replace('[', '\\[').replace(']', '\\]')
    
    return sanitized


def main() -> None:
    """Main entry point for the CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n⚠️  Operation cancelled by user", style="yellow")
        sys.exit(130)
    except Exception as e:
        # Sanitize error message to prevent Rich markup errors
        error_msg = _sanitize_error_message(str(e))
        console.print(f"\n❌ Unexpected error: {error_msg}", style="red")
        sys.exit(1)


if __name__ == "__main__":
    main()
