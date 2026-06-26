"""
Docker executor for isolated experiment execution.

Runs experiments in isolated Docker containers with provenance capture.
Reference: design/directory-structure.md (runner/)

Milestone 1: Basic container execution for capability experiments.
"""

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class DockerExecutor:
    """
    Execute experiments in isolated Docker containers.

    Captures provenance (image ID, commit hash, environment) for reproducibility.
    Milestone 1: Basic execution without full orchestration.
    """

    def __init__(
        self,
        image_name: str = "sci-adk-python-base",
        workspace_dir: Optional[Path] = None,
    ):
        """
        Initialize Docker executor.

        Args:
            image_name: Docker image name (must be built or pulled)
            workspace_dir: Workspace mount path (defaults to current directory)
        """
        self.image_name = image_name
        self.workspace_dir = workspace_dir or Path.cwd()

    def execute_python(
        self,
        script: str,
        script_args: Optional[List[str]] = None,
        capture_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute Python script in Docker container.

        Args:
            script: Python script content (as string)
            script_args: Optional command-line arguments for script
            capture_output: Whether to capture stdout/stderr

        Returns:
            Execution result with provenance
        """
        # Create temp script file
        script_path = self.workspace_dir / "_temp_experiment.py"
        script_path.write_text(script)

        try:
            # Build docker command
            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{self.workspace_dir}:/workspace",
                "-w",
                "/workspace",
                self.image_name,
                "python",
                str(script_path.name),
            ]

            # Add script arguments
            if script_args:
                cmd.extend(script_args)

            # Execute
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            # Capture provenance
            provenance = self._capture_provenance()

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout if capture_output else None,
                "stderr": result.stderr if capture_output else None,
                "provenance": provenance,
            }

        finally:
            # Clean up temp script
            if script_path.exists():
                script_path.unlink()

    def execute_command(
        self,
        command: List[str],
        capture_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute arbitrary command in Docker container.

        Args:
            command: Command and arguments to execute
            capture_output: Whether to capture stdout/stderr

        Returns:
            Execution result with provenance
        """
        # Build docker command
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.workspace_dir}:/workspace",
            "-w",
            "/workspace",
            self.image_name,
        ] + command

        # Execute
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=300,
        )

        # Capture provenance
        provenance = self._capture_provenance()

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout if capture_output else None,
            "stderr": result.stderr if capture_output else None,
            "provenance": provenance,
        }

    def _capture_provenance(self) -> Dict[str, Any]:
        """
        Capture provenance information for reproducibility.

        Returns:
            Provenance dict with image ID, timestamp, environment
        """
        # Get image ID
        image_id = self._get_image_id()

        # Get current git commit (if available)
        commit_hash = self._get_git_commit()

        return {
            "image_name": self.image_name,
            "image_id": image_id,
            "commit_hash": commit_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workspace": str(self.workspace_dir),
        }

    def _get_image_id(self) -> Optional[str]:
        """Get Docker image ID."""
        try:
            result = subprocess.run(
                ["docker", "images", "-q", self.image_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.workspace_dir,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None
