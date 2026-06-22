"""
Tests for Docker executor (Phase 3).

Milestone 1: Basic container execution with provenance capture.
Reference: design/milestone-1.md Phase 3
"""

import json
import pytest
from pathlib import Path

from sci_adk.runner.docker_executor import DockerExecutor


class TestDockerExecutor:
    """Test Docker executor basic functionality."""

    def test_init_default(self):
        """Test executor initialization with defaults."""
        executor = DockerExecutor()
        assert executor.image_name == "sci-adk-python-base"
        assert executor.workspace_dir == Path.cwd()

    def test_init_custom_image(self):
        """Test executor initialization with custom image."""
        executor = DockerExecutor(image_name="custom-image")
        assert executor.image_name == "custom-image"

    def test_execute_python_simple(self):
        """Test basic Python execution."""
        executor = DockerExecutor()
        result = executor.execute_python("print('Hello, World!')")

        assert result["success"] is True
        assert result["returncode"] == 0
        assert "Hello, World!" in result["stdout"]
        assert result["provenance"]["image_name"] == "sci-adk-python-base"
        assert result["provenance"]["image_id"] is not None

    def test_execute_python_with_args(self):
        """Test Python execution with arguments."""
        executor = DockerExecutor()
        script = """
import sys
for arg in sys.argv[1:]:
    print(f"arg: {arg}")
"""
        result = executor.execute_python(script, script_args=["--test", "value"])

        assert result["success"] is True
        assert "arg: --test" in result["stdout"]
        assert "arg: value" in result["stdout"]

    def test_execute_python_error(self):
        """Test Python execution with syntax error."""
        executor = DockerExecutor()
        result = executor.execute_python("print('missing quote)")

        assert result["success"] is False
        assert result["returncode"] != 0
        assert result["stderr"] is not None

    def test_execute_python_calculation(self):
        """Test Python calculation execution."""
        executor = DockerExecutor()
        result = executor.execute_python("print(2 + 2)")

        assert result["success"] is True
        assert "4" in result["stdout"]

    def test_execute_command(self):
        """Test arbitrary command execution."""
        executor = DockerExecutor()
        result = executor.execute_command(["echo", "test"])

        assert result["success"] is True
        assert "test" in result["stdout"]

    def test_provenance_capture(self):
        """Test provenance information capture."""
        executor = DockerExecutor()
        result = executor.execute_python("print('test')")

        provenance = result["provenance"]
        assert "image_name" in provenance
        assert "image_id" in provenance
        assert "timestamp" in provenance
        assert "workspace" in provenance
        assert provenance["image_name"] == "sci-adk-python-base"

    def test_git_commit_capture(self):
        """Test git commit hash capture."""
        executor = DockerExecutor()
        result = executor.execute_python("print('test')")

        # Git commit should be captured if available
        provenance = result["provenance"]
        # Commit hash may or may not be present depending on git state
        assert "commit_hash" in provenance

    def test_temp_file_cleanup(self):
        """Test temporary script file cleanup."""
        executor = DockerExecutor()
        workspace = executor.workspace_dir
        temp_files_before = list(workspace.glob("_temp_experiment.py"))

        executor.execute_python("print('test')")

        temp_files_after = list(workspace.glob("_temp_experiment.py"))
        # Temp file should be cleaned up
        assert len(temp_files_after) == len(temp_files_before)


class TestProvenanceCapture:
    """Test provenance capture mechanisms."""

    def test_image_id_capture(self):
        """Test Docker image ID capture."""
        executor = DockerExecutor()
        result = executor.execute_python("print('test')")

        assert result["provenance"]["image_id"] is not None
        # Image ID should be a SHA256 hash
        assert len(result["provenance"]["image_id"]) == 12  # Short ID format

    def test_workspace_tracking(self):
        """Test workspace directory tracking."""
        import tempfile

        # Use temporary directory that exists
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_workspace = Path(temp_dir)
            executor = DockerExecutor(workspace_dir=custom_workspace)

            result = executor.execute_python("print('test')")
            assert result["provenance"]["workspace"] == str(custom_workspace)

    def test_timestamp_format(self):
        """Test timestamp is ISO format."""
        executor = DockerExecutor()
        result = executor.execute_python("print('test')")

        timestamp = result["provenance"]["timestamp"]
        assert "T" in timestamp  # ISO format separator
        assert "Z" in timestamp or "+" in timestamp  # UTC or timezone info


class TestT1ContainerScriptSelfContained:
    """The T-1 container script must be SELF-CONTAINED (no source mount, no import).

    Bug (root-caused): the kernel ``DockerExecutor`` mounts ONLY ``workspace_dir ->
    /workspace``; it never mounts source. The old ``_T1_CONTAINER_SCRIPT`` did
    ``sys.path.insert(0, "/workspace/src")`` + ``from sci_adk.adapter.t1_encoding
    import ...``, so the container could import ``sci_adk`` ONLY when the workspace
    happened to BE the build repo. From a real research workspace (no ``src/``) the
    run failed with ``ModuleNotFoundError: No module named 'sci_adk'``.

    Fix: the script builder inlines the pure, stdlib-only ``t1_encoding`` module
    source so no ``sci_adk`` import (and no source mount) is needed. These checks
    pin that property WITHOUT requiring Docker.
    """

    def test_script_has_no_source_mount_or_sci_adk_import(self):
        from sci_adk.adapter.t1_capability import _build_t1_container_script

        script = _build_t1_container_script()
        # The two failure-causing lines must be gone.
        assert "/workspace/src" not in script
        assert "from sci_adk" not in script
        assert "import sci_adk" not in script

    def test_script_embeds_the_encoding_logic(self):
        from sci_adk.adapter.t1_capability import _build_t1_container_script

        script = _build_t1_container_script()
        # The encoding module's source is inlined (single source of truth).
        assert "def verify_injectivity" in script
        assert "class Molecule" in script
        # The driver still reconstructs molecules and prints the stats.
        assert "verify_injectivity(" in script

    def test_script_is_valid_python(self):
        from sci_adk.adapter.t1_capability import _build_t1_container_script

        script = _build_t1_container_script()
        # Must parse+compile (catches a mis-placed ``from __future__`` import, etc.).
        compile(script, "<t1>", "exec")


@pytest.mark.integration
class TestDockerIntegration:
    """Integration tests with actual Docker environment."""

    def test_docker_available(self):
        """Test that Docker daemon is accessible."""
        import subprocess

        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_image_exists(self):
        """Test that required Docker image exists."""
        import subprocess

        result = subprocess.run(
            ["docker", "images", "-q", "sci-adk-python-base"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.stdout.strip() != ""

    def test_container_cleanup(self):
        """Test that containers are properly cleaned up (--rm flag)."""
        import subprocess

        # Run a container
        subprocess.run(
            ["docker", "run", "--rm", "sci-adk-python-base", "echo", "test"],
            capture_output=True,
            timeout=10,
        )

        # Check that no containers are running
        result = subprocess.run(
            ["docker", "ps", "-q"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should be empty (all containers cleaned up)
        assert result.stdout.strip() == ""
