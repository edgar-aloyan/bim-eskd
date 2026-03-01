#!/usr/bin/env python3
"""Populate 001_server_container with electrical distribution system.

Run from server/ directory:
    .venv/bin/python scripts/populate_electrical.py
"""

import sys
from pathlib import Path

# Add server src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bim_eskd.ifc_engine.project_manager import project_manager
from bim_eskd.ifc_engine import electrical

MODEL = Path(__file__).parent.parent.parent / "projects/001_server_container/model.ifc"


def main():
    print(f"Opening {MODEL}")
    project_manager.open_project(MODEL)
    ifc = project_manager.ifc

    # Check if electrical system already exists
    existing = ifc.by_type("IfcDistributionSystem")
    if existing:
        print(f"Electrical system already exists: {existing[0].Name}")
        print("Skipping population.")
        return

    # 1. Create distribution system
    sys_result = electrical.create_distribution_system("Electrical System")
    sys_guid = sys_result["guid"]
    print(f"Created system: {sys_guid}")

    # 2. JUPITER-9000K-H1 (external, no geometry)
    # Model as IfcTransformer via direct IFC API (no engine function for transformer)
    container = project_manager.get_default_container()
    import ifcopenshell.api

    jupiter = ifcopenshell.api.run(
        "root.create_entity", ifc,
        ifc_class="IfcTransformer", name="JUPITER-9000K-H1 (35/0.8кВ, 9МВА)",
        predefined_type="VOLTAGE",
    )
    ifcopenshell.api.run(
        "spatial.assign_container", ifc,
        products=[jupiter], relating_structure=container,
    )
    pset = ifcopenshell.api.run("pset.add_pset", ifc, product=jupiter,
                                 name="Pset_TransformerTypeCommon")
    ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset, properties={
        "RatedVoltage": 35000.0,
        "RatedCurrent": 148.0,  # 9MVA / (sqrt(3) * 35kV)
    })
    electrical._assign_to_system(ifc, jupiter, sys_guid)
    print(f"Created JUPITER: {jupiter.GlobalId}")

    # 3. QF 630A x2 (external, no geometry)
    for i in range(1, 3):
        result = electrical.create_protective_device(
            name=f"QF-630A #{i}",
            device_type="CIRCUITBREAKER",
            rated_current=630.0,
            rated_voltage=800.0,
            system_guid=sys_guid,
        )
        print(f"Created QF-630A #{i}: {result['guid']}")

    # 4. Cable 0.8kV (in ground, external)
    result = electrical.create_cable_segment(
        name="Cable 0.8kV (in ground)",
        cable_type="CABLESEGMENT",
        rated_voltage=800.0,
        start_x=6.0, start_y=-5.0, start_z=-1.0,
        end_x=6.0, end_y=1.2, end_z=-0.4,
        system_guid=sys_guid,
    )
    print(f"Created cable: {result['guid']}")

    # 5. QF 400A (inside container, in switchboard area)
    result = electrical.create_protective_device(
        name="QF-400A",
        device_type="CIRCUITBREAKER",
        rated_current=400.0,
        rated_voltage=800.0,
        position_x=11.5, position_y=1.5, position_z=0.9,
        system_guid=sys_guid,
    )
    print(f"Created QF-400A: {result['guid']}")

    # 6. OPN x3 (inside container)
    for i, phase in enumerate(["L1", "L2", "L3"]):
        result = electrical.create_protective_device(
            name=f"OPN-0.66 {phase}",
            device_type="VARISTOR",
            rated_current=0.0,
            rated_voltage=660.0,
            position_x=11.5 + i * 0.25, position_y=1.8, position_z=0.9,
            system_guid=sys_guid,
        )
        print(f"Created OPN {phase}: {result['guid']}")

    # 7. Main busbar L1-L2-L3-PE-N
    result = electrical.create_distribution_board(
        name="Main Bus L1-L2-L3-PE(=N)",
        board_type="SWITCHBOARD",
        rated_current=400.0,
        rated_voltage=800.0,
        position_x=11.2, position_y=1.5, position_z=1.2,
        system_guid=sys_guid,
    )
    print(f"Created main bus: {result['guid']}")

    # 8. Assign existing TRS-160 to system
    trs_guid = "3CDyaw6VT0S8Z6QTe4WLax"  # This is the door, need to find transformer
    # Find the transformer in the model
    transformers = ifc.by_type("IfcTransformer")
    trs_found = None
    for t in transformers:
        if t.Name and "160" in t.Name:
            trs_found = t
            break

    if not trs_found:
        # Create ТРС-160 as IfcTransformer (it might only exist as generic element)
        trs = ifcopenshell.api.run(
            "root.create_entity", ifc,
            ifc_class="IfcTransformer", name="TRS-160 (0.8/0.4кВ, 160кВА)",
            predefined_type="VOLTAGE",
        )
        ifcopenshell.api.run(
            "spatial.assign_container", ifc,
            products=[trs], relating_structure=container,
        )
        pset = ifcopenshell.api.run("pset.add_pset", ifc, product=trs,
                                     name="Pset_TransformerTypeCommon")
        ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset, properties={
            "RatedVoltage": 800.0,
            "RatedCurrent": 115.5,  # 160kVA / (sqrt(3) * 0.8kV)
        })
        # Position at transformer location in switchboard
        from bim_eskd.ifc_engine.ifc_utils import create_transformation_matrix
        mat = create_transformation_matrix(11.562, 1.559, 0.770)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", ifc,
            product=trs, matrix=mat.tolist(),
        )
        electrical._assign_to_system(ifc, trs, sys_guid)
        print(f"Created TRS-160: {trs.GlobalId}")
    else:
        electrical._assign_to_system(ifc, trs_found, sys_guid)
        print(f"Assigned TRS-160: {trs_found.GlobalId}")

    # 9. Secondary busbar L1'-L2'-L3'
    result = electrical.create_distribution_board(
        name="Secondary Bus L1'-L2'-L3'",
        board_type="DISTRIBUTIONBOARD",
        rated_current=200.0,
        rated_voltage=400.0,
        position_x=11.2, position_y=1.5, position_z=1.5,
        system_guid=sys_guid,
    )
    print(f"Created secondary bus: {result['guid']}")

    project_manager.save()
    print(f"\nSaved to {MODEL}")

    # Summary
    print(f"\nElectrical elements in model:")
    for cls in ("IfcDistributionSystem", "IfcTransformer",
                "IfcProtectiveDevice", "IfcElectricDistributionBoard",
                "IfcCableSegment"):
        entities = ifc.by_type(cls)
        if entities:
            print(f"  {cls}: {len(entities)}")
            for e in entities:
                print(f"    - {e.Name} ({e.GlobalId})")


if __name__ == "__main__":
    main()
