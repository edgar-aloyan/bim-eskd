"""IFC project manager — replaces Bonsai's IfcStore.

Manages the in-memory IFC file, spatial structure, and persistence.
"""

import logging
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.unit

logger = logging.getLogger(__name__)


class ProjectManager:
    """Manages one IFC project at a time."""

    def __init__(self):
        self._ifc: Optional[ifcopenshell.file] = None
        self._path: Optional[Path] = None
        self._default_container = None

    @property
    def ifc(self) -> ifcopenshell.file:
        if self._ifc is None:
            raise RuntimeError("No IFC project open. Call open_project() or new_project() first.")
        return self._ifc

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def is_open(self) -> bool:
        return self._ifc is not None

    def open_project(self, path: str | Path) -> ifcopenshell.file:
        """Open an existing IFC file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"IFC file not found: {path}")
        self._ifc = ifcopenshell.open(str(path))
        self._path = path
        self._default_container = None
        logger.info(f"Opened IFC: {path} ({len(self._ifc.by_type('IfcProduct'))} products)")
        return self._ifc

    def new_project(
        self,
        path: str | Path,
        project_name: str = "BIM-ESKD Project",
        schema: str = "IFC4",
    ) -> ifcopenshell.file:
        """Create a new IFC file with basic spatial structure."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        ifc = ifcopenshell.file(schema=schema)

        # Create project
        project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name=project_name)

        # Units: meters
        ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "METRES"})

        # Geometric contexts
        model_ctx = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
        ifcopenshell.api.run(
            "context.add_context",
            ifc,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=model_ctx,
        )
        ifcopenshell.api.run(
            "context.add_context",
            ifc,
            context_type="Model",
            context_identifier="Axis",
            target_view="GRAPH_VIEW",
            parent=model_ctx,
        )

        # Spatial structure: Site -> Building -> Storey
        site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Site")
        ifcopenshell.api.run("aggregate.assign_object", ifc, products=[site], relating_object=project)

        building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Building")
        ifcopenshell.api.run("aggregate.assign_object", ifc, products=[building], relating_object=site)

        storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Level 0")
        ifcopenshell.api.run("aggregate.assign_object", ifc, products=[storey], relating_object=building)

        self._ifc = ifc
        self._path = path
        self._default_container = storey
        self.save()

        logger.info(f"Created new IFC project: {path}")
        return ifc

    def save(self, path: str | Path | None = None) -> Path:
        """Save the IFC file to disk."""
        save_path = Path(path) if path else self._path
        if save_path is None:
            raise RuntimeError("No save path set")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        self.ifc.write(str(save_path))
        self._path = save_path
        logger.info(f"Saved IFC: {save_path}")
        return save_path

    def get_default_container(self):
        """Get or find the default spatial container (IfcBuildingStorey)."""
        if self._default_container is not None:
            return self._default_container
        storeys = self.ifc.by_type("IfcBuildingStorey")
        if storeys:
            self._default_container = storeys[0]
            return self._default_container
        raise RuntimeError("No IfcBuildingStorey found in the project")

    def set_default_container(self, guid: str):
        """Set the default container by GUID."""
        element = self.ifc.by_guid(guid)
        if element is None:
            raise ValueError(f"Element not found: {guid}")
        self._default_container = element

    def get_element(self, guid: str):
        """Get an IFC element by GlobalId."""
        return self.ifc.by_guid(guid)

    def get_products(self, ifc_class: str = "IfcProduct") -> list:
        """List all products of given class."""
        return self.ifc.by_type(ifc_class)

    def close(self):
        """Close the current project."""
        self._ifc = None
        self._path = None
        self._default_container = None


# Singleton instance
project_manager = ProjectManager()
