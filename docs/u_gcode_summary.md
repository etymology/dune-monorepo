

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
for n \in [0,399]:
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
    BtoA(foot_bottom_end + n + 1)

the actual wrapping recipe

goto(7174,0)
BtoA(foot_bottom_end)
for n \in [0,399]:

























































































































































































































































































































































































































































[[]]
    increment (-x_pull_in,0)
    B(top_foot_end + 399 - n)
    BtoA(top_foot_end + 399 - n)
    increment (0,-y_pull_in)
    if near_comb(top_foot_end + 399 - n):
        increment (-3*y_pull_in,0)
    BtoA(bottom_head_end+n)
    B(bottom_head_end+n)
    increment (0,y_pull_in)
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

after wrap 399, the last pin is foot_top_end, then increment(x_pull_in,0)