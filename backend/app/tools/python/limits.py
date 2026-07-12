from pydantic import BaseModel


class SandboxResourceLimits(BaseModel):
    max_memory_mb: int = 256
    max_cpu_percent: int = 50
    max_execution_time_sec: int = 30
    network_enabled: bool = False
