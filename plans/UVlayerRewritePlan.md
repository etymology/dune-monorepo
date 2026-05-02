# End to end change to diagonal layer workflow

The desired UV workflow is similar to the one we do today but different mainly in the area of solving for the machine calibration, in the nature of the calibration artifacts stored and how they are used.

Today the UV calibration routines save json files with the winder coordinates (i.e. "camera coordinates") which have had the camera wire offset added to them. These adjusted positions are then used by the solver called by the ~anchorToTarget macro to determine the command position of the winder in order to stretch a wire from the anchor pin to the target pin, tangent to both pins on the correct sides of the pins, and taking into account that the wire does not actually go to the camera position but to a position displaced from the camera position by a certain amount. This displacement is the "camera wire offset" plus the "arm correction" which will be explained in further detail below.

The problem is that the camera wire offset is not in fact constant. It varies depending on the pose of the winder (for example, how far the z arm is extended). Therefore it does not make sense to store the calibration file with the offset baked in. Instead the anchorToTarget macro should consume calibration camera space coordinate pins and solve for thee final pose of hte winder using per pose calculations of the camera wire offset.

In a UV layer recipe there are 12 pin placements. Currently, the user must go to the gcode generation page to add offsets to each of the 12 placement points in order for the wire to go to the right place. I want to change the way this works so that, on the APA.html page, after executing a gcode command within a recipe, the user will manually move the winder to the correct position then use a dialogue box to select "use current position" which will record the xyz position of the winder and the gcode line that was supposed to have generated it on the machine calibration page, and also modify the loaded gcode adding offsets in x y and z in order to move the winder from the calculated position to the recorded position. This will require addition of offset in Z as offset(x,y) currently.

The offsets recorded for one gcode line get propagated to all gcode lines with the same label (e.g. Top B Corner). The dialogue box is located on the APA.html page next to the executing gcode panel.

Finally, when we have collected several calibration points, we can run the machine calibration solver in the machine calibration page. This will calculate the implied camera wire offset by the collected gcode lines and their resulting points and the roller positions.

The reason why there are different camera wire offsets is because the wire, under tension, pulls the winding head with its rollers to one side or another. Because the frame distortions are somewhat arbitrary and depend on the extension of the Z arm, which gets pulled to one side or another or up or down. This is why we need individal offsets per pin placement. But we also want to establish two basic values for the camera wire offset: one for when the winding head is on the stage and one for when it is on the fixed side.

Once the machine calibration has been calculated we save the camera wire offsets and roller offsets to the machine calibration file and regenerate the gcode offsets.

For the solution of the Z plane, change the way that the plane is calculated as follows: the B pins form a rectangular loop roughly parallel in the xy plane with various offsets. The A plane is displaced from the B plane by the board width, which is equal to 130mm for U, 120mm for V. The new solver should, using the knowledge of the position of the winder and the fact that the wire touches the pins, attempts to solve for a continuous loop for the b pin positions. In other words, the B pins may not be planar but must be continuous.

The calibration files are generated using the Calibrate.html page.

B pins' xy coordinates are found by moving winder calibration camera on the B side to the pin and recording the xy position of the winder. The A pins are then decided based on a transformation from the nominal geometry based on the B side.

We should change the way that the pins are named to layer, side, number. where layer is in UV, side is in AB and number is in 1-2399 for V and 1-2401 for U. So the pins are named UA1 or VB23.

Create a Pin class which has these there properties and the derived properites "face" and "tangent_normal_sign"

``` python
_FACE_RANGES = {
  "U": {
    "head": (1, 400),
    "bottom": (401, 1200),
    "foot": (1201, 1601),
    "top": (1602, 2401),
  },
  "V": {
    "head": (1, 399),
    "bottom": (400, 1199),
    "foot": (1200, 1599),
    "top": (1600, 2399),
  },
}
```
and

``` python
def tangent_sides(layer: str, side: str, n: int) -> tuple[int, int]:
    x = 1 if (
        (layer == "U" and n <= 1200) or
        (layer == "V" and (n <= 399 or n >= 1600))
    ) else -1

    y = (1 if (layer, side) in {("U", "B"), ("V", "A")} else -1) * x
    return x, y
```

``` python
_ENDPOINT_PINS = {
  "U": (
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320,
    321, 360, 361, 400, 401, 424, 425, 449, 450, 473, 474, 510, 511, 547, 548,
    584, 585, 621, 622, 658, 659, 695, 696, 732, 733, 769, 770, 806,
    807, 843, 844, 880, 881, 917, 918, 954, 955, 991, 992, 1028, 1029, 1065,
    1066, 1102, 1103, 1139, 1140, 1176, 1177, 1200, 1201, 1240, 1241, 1280,
    1281, 1320, 1321, 1360, 1361, 1400, 1401, 1440, 1441, 1480, 1481, 1520,
    1521, 1560, 1561, 1601, 1602, 1625, 1626, 1662, 1663, 1699, 1700, 1736,
    1737, 1773, 1774, 1810, 1811, 1847, 1848, 1884, 1885, 1921, 1922, 1958,
    1959, 1995, 1996, 2032, 2033, 2069, 2070, 2106, 2107, 2143,
    2144, 2180, 2181, 2217, 2218, 2254, 2255, 2291, 2292, 2328, 2329, 2352,
    2353, 2377, 2378, 2401,
  ),
  "V": (
    1, 40, 41, 80, 81, 120, 121, 160, 161, 200, 201, 240, 241, 280, 281, 320,
    321, 360, 361, 399, 400, 423, 424, 448, 449, 472, 473, 509, 510, 546, 547,
    583, 584, 620, 621, 657, 658, 694, 695, 731, 732, 768, 769, 805,
    806, 842, 843, 879, 880, 916, 917, 953, 954, 990, 991, 1027, 1028, 1064,
    1065, 1101, 1102, 1138, 1139, 1175, 1176, 1199, 1200, 1239, 1240, 1279,
    1280, 1319, 1320, 1359, 1360, 1399, 1400, 1439, 1440, 1479, 1480, 1519,
    1520, 1559, 1560, 1599, 1600, 1623, 1624, 1660, 1661, 1697, 1698, 1734,
    1735, 1771, 1772, 1808, 1809, 1845, 1846, 1882, 1883, 1919, 1920, 1956,
    1957, 1993, 1994, 2030, 2031, 2067, 2068, 2104, 2105, 2141,
    2142, 2178, 2179, 2215, 2216, 2252, 2253, 2289, 2290, 2326, 2327, 2350,
    2351, 2375, 2376, 2399,
  ),
}
```

Simultaneously centralize the geometry helpers in a module separate from dune_winder and dune_tension which will be imported from them both, dune_geometry. This package will calculate and expose wire paths which will be consumed by dune_tension and dune_winder.
