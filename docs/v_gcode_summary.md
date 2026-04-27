# V-Layer Pin Succession

This summary describes the intrinsic V-layer pin geometry as a single continuous
wire path. The tension system later views parts of this path as separate
measurable segments on A and B sides, but the winder creates them by carrying
one wire around pins in the succession below.

Terminology:

- `top`, `bottom`, `head`, and `foot` are APA frame edges.
- `A` and `B` are APA sides.
- `B(n)` is pin `n` on the B side.
- `BtoA(n)` is the A-side pin at the same physical position as B-side pin `n`.

For V:

```text
BtoA(n) = A(1 + ((399 - n) mod 2399))
```

There are 400 wraps. This document numbers them `n in [0, 399]`; recipe output
numbers them `1` through `400`.

Named V edge pins, expressed in canonical B-side numbering:

```text
bottom_foot_end = 1199
bottom_head_end = 400
top_foot_end = 1600
top_head_end = 2399
foot_bottom_end = 1200
foot_top_end = 1599
head_bottom_end = 399
head_top_end = 1
```

## Continuous Pin Path

For wrap `n`, the wire visits these pin positions in order:

```text
B(bottom_head_end + n)
B(top_foot_end + 399 - n)
BtoA(top_foot_end + 399 - n)
BtoA(foot_bottom_end + n)
B(foot_bottom_end + n)
B(bottom_foot_end - n)
BtoA(bottom_foot_end - n)
BtoA(top_head_end - 399 + n)
B(top_head_end - 399 + n)
B(head_bottom_end - n)
BtoA(head_bottom_end - n)
BtoA(bottom_head_end + n + 1)
```

The last point of wrap `n` continues to the first point of wrap `n + 1`:

```text
BtoA(bottom_head_end + n + 1)
  -> B(bottom_head_end + n + 1)
```

So the full V layer is the concatenation of all 400 wrap paths. Adjacent points
in this succession define the applied wire spans. The side changes, such as
`B(...) -> BtoA(...)`, are part of the wire geometry, not merely machine
transfer bookkeeping.

## Recipe Motions

The recipe adds pull-ins and transfer motions around the same pin succession.
Those movements guide placement, but they do not change the ordered pin path.

Parameters:

```text
x_pull_in = 70 mm
y_pull_in = 50 mm
```

Abstracted recipe:

```text
for n in [0, 399]:
    anchorToTarget(B(bottom_head_end + n), B(top_foot_end + 399 - n))
    increment(0, y_pull_in)
    if near_comb(bottom_head_end + n):
        increment(3 * y_pull_in, 0)

    anchorToTarget(B(top_foot_end + 399 - n), BtoA(top_foot_end + 399 - n))
    increment(0, -y_pull_in)
    if near_comb(top_foot_end + 399 - n):
        increment(3 * y_pull_in, 0)

    anchorToTarget(
        BtoA(top_foot_end + 399 - n),
        BtoA(foot_bottom_end + n)
    )
    anchorToTarget(BtoA(foot_bottom_end + n), B(foot_bottom_end + n))
    increment(-x_pull_in, 0)

    anchorToTarget(B(foot_bottom_end + n), B(bottom_foot_end - n))
    anchorToTarget(B(bottom_foot_end - n), BtoA(bottom_foot_end - n))
    increment(0, y_pull_in)
    if near_comb(bottom_foot_end - n):
        increment(-3 * y_pull_in, 0)

    anchorToTarget(
        BtoA(bottom_foot_end - n),
        BtoA(top_head_end - 399 + n)
    )
    anchorToTarget(BtoA(top_head_end - 399 + n), B(top_head_end - 399 + n))
    increment(0, -y_pull_in)
    if near_comb(top_head_end - 399 + n):
        increment(-3 * y_pull_in, 0)

    anchorToTarget(B(top_head_end - 399 + n), B(head_bottom_end - n))
    anchorToTarget(B(head_bottom_end - n), BtoA(head_bottom_end - n))
    increment(x_pull_in, 0)

    anchorToTarget(
        BtoA(head_bottom_end - n),
        BtoA(bottom_head_end + n + 1)
    )
```
