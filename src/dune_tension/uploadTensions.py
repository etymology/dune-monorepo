from dune_tension.m2m.common import ConnectToAPI, EditAction
from dune_tension.summaries import get_expected_range, get_tension_series
from dune_tension.tensiometer_functions import make_config


def load_tension_summary(apa_name: str, layer: str) -> tuple[list, list]:
    config = make_config(apa_name=apa_name, layer=layer, side="A")
    tension_series = get_tension_series(config)
    wire_range = list(get_expected_range(layer))
    if layer in ["X", "G", "x", "g"]:
        b_side_wire_range = list(reversed(wire_range))
    else:
        b_side_wire_range = wire_range
    nan = float("nan")
    return (
        [tension_series["A"].get(wire, nan) for wire in wire_range],
        [tension_series["B"].get(wire, nan) for wire in b_side_wire_range],
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
    uploadTensions("USAPA12", "X", r"69c55b1739ec5df0071382d7")


if __name__ == "__main__":
    main()
