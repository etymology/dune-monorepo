
BtoA(layer in [U,V],pin:int):
    U: return 1 + ((400 - pin) mod 2401)
    V: return 1 + ((399 - F) mod 2399)

400 wraps, here numbered n \in [0,399] but in the recipes numbered 1-400
On wrap n
let bottom_foot_end = B1200
let bottom_head_end = B401
let top_foot_end = B1602
let top_head_end = B2401
let foot_bottom_end = B1201
let foot_top_end = B1601
let head_bottom_end = B400
let head_top_end = B1
let x_pull_in = 70mm
let y_pull_in = 50mm
for int n, B(n) is pin n on the B side and BtoA(n) is the A pin opposite that B pin on the A side.

the succession of pins alone:
pins(wrap in [0,399]):
    BtoA(foot_bottom_end + n)
    B(foot_bottom_end + n)
    B(top_foot_end + 399 - n)
    BtoA(top_foot_end + 399 - n)
    BtoA(bottom_head_end+n)
    B(bottom_head_end+n)
    B(head_bottom_end-n)
    BtoA(head_bottom_end-n)
    BtoA(top_head_end-399+n)
    B(top_head_end-399+n)
    B(bottom_foot_end-n)
    BtoA(bottom_foot_end-n)

# the actual wrapping recipe

goto(x:float, y:float) moves the winder to x,y
anchor(pin) sets the anchor pin to be used by the next pin target line. Otherwise, when we succeed in wrapping around a pin (setting the pin as a target) that pin becomes the anchor for the next segment.
B(pin:int) moves the winder to the position projected from the outbound tangent from the anchor pin (set by either anchor() or having been the previous target pin), arm-corrected position in x,y then moves the head to the target z position: either zFront for A pins or zBack for B pins, using the g106 p1 (zfront) or g106 p2.
BtoA(bpin:int) converts the b pin number to its correpsonding A pin using the formula defined above, then finds the projected winder target to wrap around that pin, as with B().
The two cases: when anchor and target pins are on the same side, move to the xy position first then the z position. When they are on opposite sides, move to the nearest transfer zone (or don't move if transfer is already enabled), move to the target z position, then move to the target xy position, which is the projected position in the xz plane of the two pins for pins on the top and bottom sides, and the projected position in the yz plane for pins on the foot and head sides. The for pins in the xz plane, the y position is just the average of the y positions of the two pins. For pins in the yz plane, the x position is just the average of the x positions of the two pins.
increment(x,y) moves the winder incrementally by (x,y)


goto(7174,0)
for n \in [0,399]:
    anchorToTarget(BtoA(foot_bottom_end),B(foot_bottom_end))
    increment (-x_pull_in,0)
    anchorToTarget(B(foot_bottom_end),B(top_foot_end + 399 - n))
    anchorToTarget(B(top_foot_end + 399 - n),BtoA(top_foot_end + 399 - n))
    increment (0,-y_pull_in)
    if near_comb(BtoA(top_foot_end + 399 - n)):
        increment (-3*y_pull_in,0)
    anchorToTarget(BtoA(top_foot_end + 399 - n),BtoA(bottom_head_end+n))
    anchorToTarget(BtoA(bottom_head_end+n),B(bottom_head_end+n))
    increment(0,y_pull_in)
    if near_comb(bottom_head_end+n):
        increment (-3*y_pull_in,0)
    B(head_bottom_end-n)
    BtoA(head_bottom_end-n)
    increment (x_pull_in,0)
    BtoA(top_head_end-399+n)
    B(top_head_end-399+n)
    increment (0,-y_pull_in)
    if near_comb(top_head_end-399+n):
        increment (3*y_pull_in,0)
    B(bottom_foot_end-n)
    BtoA(bottom_foot_end-n)
    increment (0,y_pull_in)
    if near_comb(bottom_foot_end-n):
        increment (3*y_pull_in,0)
    BtoA(foot_bottom_end + n + 1)
B(foot_top_end)
increment(x_pull_in,0)
