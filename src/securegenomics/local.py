"""
Local analysis for SecureGenomics CLI.

Handles local-only genomic analysis without encryption or server communication.
Perfect for exploratory analysis, education, and offline workflows.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from securegenomics.config import ConfigManager
from securegenomics.protocol import ProtocolManager

console = Console()

class LocalAnalyzer:
    """Manages local-only genomic analysis."""
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.protocol_manager = ProtocolManager()
    
    def analyze(self, protocol_name: str, vcf_path: Path):
        """Run local analysis on VCF file using specified protocol."""
        try:
            console.print(f"Starting local analysis: {protocol_name}")
            console.print(f"Input file: {vcf_path}")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                # Verify VCF file
                task = progress.add_task("Validating VCF file...", total=100)
                
                if not vcf_path.exists():
                    raise Exception(f"VCF file not found: {vcf_path}")
                
                progress.update(task, advance=25)
                
                # Fetch protocol if needed
                progress.update(task, description="Preparing protocol...")
                protocol_dir = self.config_manager.get_protocol_cache_dir(protocol_name)
                
                if not protocol_dir.exists():
                    console.print(f"Protocol {protocol_name} not cached, fetching...")
                    self.protocol_manager.fetch(protocol_name)
                
                progress.update(task, advance=25)
                
                # Verify protocol
                progress.update(task, description="Verifying protocol...")
                if not self.protocol_manager.verify(protocol_name):
                    raise Exception(f"Protocol {protocol_name} verification failed")
                
                progress.update(task, advance=50, completed=True)
                
                # Execute protocol analysis
                task = progress.add_task("Running local compute...", total=None)
                
                # Execute the protocol's local analysis function
                local_compute_result = self.protocol_manager.execute(
                    protocol_name=protocol_name,
                    operation="local_compute",
                    vcf_path=str(vcf_path)
                )
                
                # tell user that local compute is done, and now interpreting
                console.print("Local compute is done, now interpreting...")
                
                local_interpret_result = self.protocol_manager.execute(
                    protocol_name=protocol_name,
                    operation="local_interpret",
                    prs=local_compute_result,
                )
                
                progress.update(task, completed=True)
            
            # Log audit event
            self.config_manager.log_audit_event("local_analyze", {
                "protocol": protocol_name,
                "vcf_file": str(vcf_path),
                "file_size": vcf_path.stat().st_size,
                "success": True
            })
            
            print(local_interpret_result)
            
        except Exception as e:
            # Log failed analysis
            self.config_manager.log_audit_event("local_analyze", {
                "protocol": protocol_name,
                "vcf_file": str(vcf_path),
                "success": False,
                "error": str(e)
            })
            raise Exception(f"Local analysis failed: {e}")
    
    
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        import datetime
        return datetime.datetime.utcnow().isoformat()
        
    def list_local_protocols(self) -> List[str]:
        """List protocols that support local analysis."""
        try:
            protocols = self.protocol_manager.list_protocols()
            return [p.name for p in protocols if p.local_supported]
        except Exception:
            return []
    
    def get_protocol_info(self, protocol_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific protocol."""
        try:
            protocols = self.protocol_manager.list_protocols()
            for protocol in protocols:
                if protocol.name == protocol_name:
                    return {
                        "name": protocol.name,
                        "description": protocol.description,
                        "version": protocol.version,
                        "analysis_type": protocol.analysis_type,
                        "local_supported": protocol.local_supported,
                        "github_url": protocol.github_url
                    }
            return None
        except Exception:
            return None 