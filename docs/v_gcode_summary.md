

BtoA(layer in [U,V],pin:int):
    U: return 1 + ((400 - pin) mod 2401)
    V: return 1 + ((399 - F) mod 2399)

400 wraps, here numbered n \in [0,399] but in the recipes numbered 1-400
On wrap n
let bottom_foot_end = 1199
let bottom_head_end = 400
let top_foot_end = 1600
let top_head_end = 2399
let foot_bottom_end = 1200
let foot_top_end = 1599
let head_bottom_end = 399
let head_top_end = 1
let x_pull_in = 70mm
let y_pull_in = 50mm
for int n, B(n) is pin n on the B side and BtoA(n) is the A pin opposite that B pin on the A side.

the succession of pins alone:
for n \in [0,399]:
    B(bottom_head_end+n)
    B(top_foot_end + 399 - n)
    BtoA(top_foot_end + 399 - n)
    BtoA(foot_bottom_end+n)
    B(foot_bottom_end+n)
    B(bottom_foot_end-n)
    BtoA(bottom_foot_end-n)
    BtoA(top_head_end-399+n)
    B(top_head_end-399+n)
    B(head_bottom_end-n)
    BtoA(head_bottom_end-n)
    BtoA(bottom_head_end+n+1)

the actual wrapping recipe
for n \in [0,399]:
    B(bottom_head_end+n)
    B(top_foot_end + 399 - n)
    BtoA(top_foot_end + 399 - n)
    BtoA(foot_bottom_end+n)
    B(foot_bottom_end+n)
    B(bottom_foot_end-n)
    BtoA(bottom_foot_end-n)
    BtoA(top_head_end-399+n)
    B(top_head_end-399+n)
    B(head_bottom_end-n)
    BtoA(head_bottom_end-n)
    BtoA(bottom_head_end+n+1)

for n \in [0,399]:
    B(bottom_head_end+n)
        increment (0,y_pull_in)
        if near_comb(bottom_head_end+n):
            increment (3*y_pull_in,0)
    B(top_foot_end + 399 - n)
    BtoA(top_foot_end + 399 - n)
        increment (0,-y_pull_in)
        if near_comb(bottom_head_end+n):
            increment (3*y_pull_in,0)
    BtoA(foot_bottom_end+n)
    B(foot_bottom_end+n)
        increment (-x_pull_in,0)
    B(bottom_foot_end-n)
    BtoA(bottom_foot_end-n)
        increment (0,y_pull_in)
        if near_comb(bottom_head_end+n):
            increment (-3*y_pull_in,0)
    BtoA(top_head_end-399+n)
    B(top_head_end-399+n)
        increment (0,-y_pull_in)
        if near_comb(bottom_head_end+n):
            increment (-3*y_pull_in,0)
    B(head_bottom_end-n)
    BtoA(head_bottom_end-n)
        increment (x_pull_in,0)
    BtoA(bottom_head_end+n+1)
