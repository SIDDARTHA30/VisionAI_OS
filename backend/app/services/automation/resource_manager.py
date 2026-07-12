import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manages active system resource cleanups, temp workspaces, and child processes."""

    def __init__(self):
        self._active_subprocesses: Set[subprocess.Popen] = set()
        self._workspaces_to_clean: Set[Path] = set()

    def register_subprocess(self, proc: subprocess.Popen) -> None:
        self._active_subprocesses.add(proc)

    def unregister_subprocess(self, proc: subprocess.Popen) -> None:
        self._active_subprocesses.discard(proc)

    def register_workspace(self, path: Path) -> None:
        self._workspaces_to_clean.add(path)

    def clean_workspace(self, path: Path) -> None:
        """Deletes sandboxed temporary directories."""
        if path.exists():
            try:
                shutil.rmtree(path)
                logger.info(f"Cleaned up workspace directory: {path}")
            except Exception as e:
                logger.error(f"Failed to clean workspace directory {path}: {e}")
        self._workspaces_to_clean.discard(path)

    def cleanup_all(self) -> None:
        """Gracefully terminates active subprocesses and cleans workspaces on task cancel/fail."""
        # 1. Terminate subprocesses
        for proc in list(self._active_subprocesses):
            try:
                poll_val = proc.poll() if hasattr(proc, "poll") else proc.returncode
                if poll_val is None:
                    proc.terminate()
                    logger.info(f"Terminated active child subprocess: PID {proc.pid}")
            except Exception as e:
                try:
                    proc.kill()
                    logger.warning(f"Killed child process PID {proc.pid} after termination failed: {e}")
                except Exception:
                    pass
        self._active_subprocesses.clear()

        # 2. Cleanup folders
        for ws in list(self._workspaces_to_clean):
            self.clean_workspace(ws)


# Global resource manager
resource_manager = ResourceManager()
