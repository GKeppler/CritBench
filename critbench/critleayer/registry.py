#!/usr/bin/env python3
"""
CritLayer Tool Registry — register and resolve OT tools for LLM agents.

Each task YAML specifies which tools are allowed; the registry filters accordingly.
Tools are decorated with @function_tool from the OpenAI Agents SDK.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Global singleton registry
_TOOL_REGISTRY: Dict[str, Any] = {}


def register_tool(tool_fn: Any) -> Any:
    """Register a @function_tool-decorated function in the global registry.

    The tool's ``name`` attribute (set by @function_tool) is used as the key.
    If the function is not yet wrapped by @function_tool, its __name__ is used.
    """
    name = getattr(tool_fn, "name", None) or getattr(tool_fn, "__name__", str(tool_fn))
    if name in _TOOL_REGISTRY:
        logger.warning("Tool %r is already registered — overwriting", name)
    _TOOL_REGISTRY[name] = tool_fn
    logger.debug("Registered tool: %s", name)
    return tool_fn


def get_tool(name: str) -> Any:
    """Retrieve a single tool by name."""
    if name not in _TOOL_REGISTRY:
        raise KeyError(f"Tool {name!r} not found in registry. Available: {list(_TOOL_REGISTRY.keys())}")
    return _TOOL_REGISTRY[name]


def get_tools(names: List[str]) -> List[Any]:
    """Retrieve a list of tools by name.  Raises KeyError for missing tools."""
    tools = []
    for name in names:
        tools.append(get_tool(name))
    return tools


def get_all_tools() -> List[Any]:
    """Return every registered tool."""
    return list(_TOOL_REGISTRY.values())


def list_tool_names() -> List[str]:
    """Return the names of every registered tool."""
    return list(_TOOL_REGISTRY.keys())


def clear_registry() -> None:
    """Remove all registered tools (useful for testing)."""
    _TOOL_REGISTRY.clear()
