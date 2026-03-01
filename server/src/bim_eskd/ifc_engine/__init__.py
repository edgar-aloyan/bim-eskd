"""IFC engine — pure ifcopenshell operations, no Blender dependency."""

from .project_manager import ProjectManager, project_manager

__all__ = ["ProjectManager", "project_manager"]
