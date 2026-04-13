import pandas as pd

from dune_tension.m2m.common import ConnectToAPI, EditAction
from dune_tension.paths import data_path
from dune_tension.summaries import get_expected_range


def load_tension_summary(apa_name: str, layer: str) -> tuple[list, list]:
    csv_path = data_path(
        "tension_summaries", f"tension_summary_{apa_name}_{layer}.csv"
    )
    df = pd.read_csv(csv_path).set_index("wire_number")
    wire_range = list(get_expected_range(layer))
    if layer in ["X", "G", "x", "g"]:
        b_side_wire_range = list(reversed(wire_range))
    else:
        b_side_wire_range = wire_range
    nan = float("nan")
    return (
        [df["A"].get(wire, nan) for wire in wire_range],
        [df["B"].get(wire, nan) for wire in b_side_wire_range],
    )


def uploadTensions(apa_name: str, layer: str, create_layer_action_id: str) -> None:
    connection, headers = ConnectToAPI()

    # actionTypeFormID = "x_tension_testing"  # This name is misleading: the action type form is the same for ALL LAYERS
    # componentUUID = t.get_uuid()  # This is the identity of APA

    # actionData = {
    #     "apaLayer": t.layer,
    #     "location": "Chicago",
    #     "measurementSystem": "Laser #1",
    #     "date": str(datetime.now()),
    # }

    # create_layer_action_id = PerformAction(
    #     actionTypeFormID, componentUUID, actionData, connection, headers
    # )

    # print(f" Successfully performed action with ID: {create_layer_action_id}")

    tensions_sideA, tensions_sideB = load_tension_summary(apa_name, layer)
    print(tensions_sideA, tensions_sideB)
    print(f" Uploading {len(tensions_sideA)} tensions for APA {apa_name} layer {layer}...")
    actionData_fields = [
        "measuredTensions_sideA",
        "measuredTensions_sideB",
        "replacedWireSegs",
        "comments",
    ]
    actionData_values = [
        tensions_sideA,
        tensions_sideB,
        "All wire segments are within specified tolerance.",
        "This is an existing single layer tension measurements action, edited via M2M",
    ]

    edit_layer_action_id = EditAction(
        create_layer_action_id,
        actionData_fields,
        actionData_values,
        connection,
        headers,
    )
    print(f" Successfully edited action with ID: {edit_layer_action_id}")

    connection.close()


def main() -> None:
    uploadTensions("APAUK007", "V", r"69d6a79b07c1c59eb7b34781")


if __name__ == "__main__":
    main()
