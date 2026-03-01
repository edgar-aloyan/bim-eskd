"""Pure ifcopenshell utilities — no bpy dependency.

Ported from bonsai-mcp's blender_addon/api/ifc_utils.py, removing all
Blender/Bonsai imports. Provides geometry contexts, matrix creation,
and unit helpers.
"""

import math
from typing import Optional

import numpy as np
import ifcopenshell
import ifcopenshell.util.unit


def get_or_create_body_context(ifc_file: ifcopenshell.file):
    """Get the 'Body' representation context, or create it."""
    for ctx in ifc_file.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body" and ctx.TargetView == "MODEL_VIEW":
            return ctx

    # Create parent Model context first
    model_ctx = None
    for ctx in ifc_file.by_type("IfcGeometricRepresentationContext"):
        if ctx.ContextType == "Model" and not hasattr(ctx, "ParentContext"):
            model_ctx = ctx
            break
    if model_ctx is None:
        model_ctx = ifcopenshell.api.run(
            "context.add_context", ifc_file, context_type="Model"
        )

    return ifcopenshell.api.run(
        "context.add_context",
        ifc_file,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )


def get_or_create_axis_context(ifc_file: ifcopenshell.file):
    """Get the 'Axis' representation context, or create it."""
    for ctx in ifc_file.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Axis" and ctx.TargetView == "GRAPH_VIEW":
            return ctx

    model_ctx = None
    for ctx in ifc_file.by_type("IfcGeometricRepresentationContext"):
        if ctx.ContextType == "Model" and not hasattr(ctx, "ParentContext"):
            model_ctx = ctx
            break
    if model_ctx is None:
        model_ctx = ifcopenshell.api.run(
            "context.add_context", ifc_file, context_type="Model"
        )

    return ifcopenshell.api.run(
        "context.add_context",
        ifc_file,
        context_type="Model",
        context_identifier="Axis",
        target_view="GRAPH_VIEW",
        parent=model_ctx,
    )


def calculate_unit_scale(ifc_file: ifcopenshell.file) -> float:
    """Get the unit scale factor (m → model units)."""
    try:
        return ifcopenshell.util.unit.calculate_unit_scale(ifc_file)
    except Exception:
        return 1.0


def create_transformation_matrix(
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    rotation_x: float = 0.0,
    rotation_y: float = 0.0,
    rotation_z: float = 0.0,
) -> np.ndarray:
    """Create a 4x4 transformation matrix from position and Euler angles (degrees)."""
    rx = math.radians(rotation_x)
    ry = math.radians(rotation_y)
    rz = math.radians(rotation_z)

    # Rotation matrices
    Rx = np.array([
        [1, 0, 0],
        [0, math.cos(rx), -math.sin(rx)],
        [0, math.sin(rx), math.cos(rx)],
    ])
    Ry = np.array([
        [math.cos(ry), 0, math.sin(ry)],
        [0, 1, 0],
        [-math.sin(ry), 0, math.cos(ry)],
    ])
    Rz = np.array([
        [math.cos(rz), -math.sin(rz), 0],
        [math.sin(rz), math.cos(rz), 0],
        [0, 0, 1],
    ])

    R = Rz @ Ry @ Rx

    mat = np.eye(4)
    mat[:3, :3] = R
    mat[0, 3] = position_x
    mat[1, 3] = position_y
    mat[2, 3] = position_z
    return mat


def create_custom_rotation_matrix(
    position: tuple[float, float, float],
    x_axis: tuple[float, float, float],
    y_axis: tuple[float, float, float],
    z_axis: tuple[float, float, float],
) -> np.ndarray:
    """Create a 4x4 matrix from explicit axes and position."""
    mat = np.eye(4)
    mat[0, :3] = x_axis
    mat[1, :3] = y_axis
    mat[2, :3] = z_axis
    mat[0, 3] = position[0]
    mat[1, 3] = position[1]
    mat[2, 3] = position[2]
    return mat


def create_circular_polyline(
    radius: float, segments: int = 36
) -> list[tuple[float, float]]:
    """Create a circular polyline for slabs/profiles."""
    points = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    points.append(points[0])  # close the loop
    return points
