"""
CritLayer — OT tool abstraction layer for CritBench.

Importing this package triggers auto-registration of every tool module.
After import, use ``registry.get_tools(names)`` to resolve a task's
allowed tool set.
"""

# Auto-register all tool modules so the registry is populated on import.
from . import tools_common   # noqa: F401
from . import tools_pcap     # noqa: F401
from . import tools_mms      # noqa: F401
from . import tools_goose    # noqa: F401
from . import tools_iec104   # noqa: F401
from . import tools_scl      # noqa: F401
from . import tools_modbus   # noqa: F401
from .registry import get_tools, get_all_tools, list_tool_names  # noqa: F401
