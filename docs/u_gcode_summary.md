BtoA(b_pin) converts a B pin to the opposite A pin using modular arithmetic.

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

for n \in [0,399]
foot_bottom_end + n
top_foot_end + 399 - n
BtoA(top_foot_end + 399 - n)
BtoA(bottom_head_end+n)
bottom_head_end+n
head_bottom_end+n
BtoA(head_bottom_end+n)
BtoA(top_head_end-399+n)
top_head_end-399+n
bottom_foot_end-n
BtoA(bottom_foot_end-n)
BtoA(foot_bottom_end + n + 1)
