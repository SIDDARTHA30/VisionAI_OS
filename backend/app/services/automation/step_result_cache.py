import hashlib
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StepResultCache:
    """Caches step executions to bypass repetitive identical operations."""

    def __init__(self):
        # In-memory dictionary cache map
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _generate_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Serializes tool signature arguments into MD5 keys."""
        serialized = json.dumps(arguments, sort_keys=True)
        raw = f"{tool_name}:{serialized}".encode("utf-8")
        return hashlib.md5(raw).hexdigest()

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch cached output parameters if match occurs."""
        key = self._generate_key(tool_name, arguments)
        if key in self._cache:
            logger.info(f"Cache hit: Reusing execution results for tool {tool_name}.")
            return self._cache[key]
        return None

    def set(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Commit result to cache."""
        key = self._generate_key(tool_name, arguments)
        self._cache[key] = result

    def clear(self) -> None:
        self._cache.clear()


# Global execution cache
step_result_cache = StepResultCache()
