# End to end change to diagonal layer workflow and

The desired UV workflow is similar to the one we do today but different mainly in the area of solving for the machine calibration, in the nature of the calibration artifacts stored and how they are used.

Today the UV calibration routines save json files with the winder coordinates (i.e. "camera coordinates") plus the camera wire offset. These adjusted positions are then used by the solver called by the ~anchorToTarget macro to determine the command position of the winder in order to stretch a wire from the anchor pin to the target pin, tangent to both pins on the correct sides of the pins, and taking into account that the wire does not actually go to the camera position but to a position displaced from the camera position by a certain amount. This displacement is the "camera wire offset" plus the "arm correction" which will be explained in further detail below.

One goal of the rewrite is to use a single coordinate system (the command positions of the winder) for all calibration artifacts and commands. This will require that the ~anchorToTarget macro be rewritten to take these raw calibration camera coordinates as inputs, as well as the machine parameters regarding the wire offset from the camera, and the rollers.

This will also change the way that the per-line offsets are calculated, the Gcode is generated, and the way that the machine calibration is solved for.

The new workflow will be as follows:

The winder has an xyz gantry loop-frame that passes around the APA. It has a z arm that can extend and retract, latch and unlatch the winding head to the A or B sides of the APA. The z arm can only be extended when in the "transfer zone" beyond the edges of the apa. It must not move or be extended when the winder is in the xy area of the apa, to avoid collision. It must also not move the z arm when it is over the conditionally present support arms.
The APA is roughly rectangular in shape with four sides in the xy plane: head bottom foot top. There is a calibration camera on the B side of the loop-frame

The calibration files are generated using the Calibrate.html page.
B pins' xy coordinates are found by moving winder calibration camera on the B side to the pin and recording the xy position of the winder. The A pins are then decided based on a transformation from the nominal geometry based on the B side.

Recorded values should be backlash corrected in x, i.e. they should try to calculate how much of the reversal window has been consumed in the movement and record the actual space position of the winder rather than the encoder position.

There is a change from how the pins were calculated on the previous model, which added the camera wire offset to the recorded values. We should NOT add this to the calibration locations. Instead the calibration files should store the camera positions. This means that the gcode interpreter will have to be able to consume these new raw calibration camera positions rather than ones already offset with the camera-wire offset.

We should change the way that the pins are named to layer, side, number. where layer is in UV, side is in AB and number is in 1-2399 for V and 1-2401 for U. So the pins are named UA1 or VB23.

The calibration files are consumed by the gcode interpreter called in APA.html. The gcode interpreter supports commands ~anchorToTarget, increment, goto, as well as the legacy G... P... commands


When a wire is placed, it has the following geometry:
It is tangent to the two pins according to the wrap_orientation rule

``` python
def tangent_sides(layer: str, side: str, n: int) -> tuple[int, int]:
    x = 1 if (
        (layer == "U" and n <= 1200) or
        (layer == "V" and (n <= 399 or n >= 1600))
    ) else -1

    y = (1 if (layer, side) in {("U", "B"), ("V", "A")} else -1) * x
    return x, y
```

The cal

From this, we can derive "face" which is in head, bottom, foot top in the following way

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

and also the board number from the list of endpoint pins (which is n between)

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
