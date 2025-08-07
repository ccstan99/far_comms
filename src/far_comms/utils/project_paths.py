#!/usr/bin/env python

from pathlib import Path


def get_project_root(start_path: Path = None) -> Path:
    """
    Find the project root directory by looking for pyproject.toml
    
    Args:
        start_path: Starting path to search from (defaults to current file's parent)
        
    Returns:
        Path to project root directory
    """
    if start_path is None:
        # Use caller's file location as starting point
        import inspect
        caller_frame = inspect.currentframe().f_back
        start_path = Path(caller_frame.f_globals['__file__']).parent
    
    current_dir = start_path
    while current_dir != current_dir.parent and not (current_dir / "pyproject.toml").exists():
        current_dir = current_dir.parent
    
    return current_dir


def get_output_dir(create: bool = True) -> Path:
    """Get the project's output directory"""
    output_dir = get_project_root() / "output"
    if create:
        output_dir.mkdir(exist_ok=True)
    return output_dir


def get_docs_dir(create: bool = False) -> Path:
    """Get the project's docs directory"""
    docs_dir = get_project_root() / "docs"
    if create:
        docs_dir.mkdir(exist_ok=True)
    return docs_dir