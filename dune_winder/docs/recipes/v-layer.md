# V Layer Recipe Description

let the constants be
transferPause in {true, false}
yPullIn = 60
xPullIn = 70
combPullFactor = 3
let offsets be a list of 12 floats

combs=[592,740,888,1043,1191,1754,1902,2050,2198]

def nearComb(pin which is PB{n} or PF{n}):
    if n is within 5 of any of the elements of combs
        True
    false

curly braces are replacements, square braces are conditional lines


Let the preamble be:
( V Layer )
X440 Y0
G106 P3
(0, ) F200 G103 PB400 PB399 PXY G105 PY30 ( BOARD GAP )

Then for wrap n in 1-399 inclusive concatenated

(------------------STARTING LOOP {n}------------------)
G109 PB{399+wrap} PRT G103 PB{1999-wrap} PB{2000-wrap} PXY {if offsets[0]!=0, G105 PX{offsets[0]}, otherwise nothing} G102 G108 (Top B corner - foot end)
G106 P3
G106 P2 [This line only if transferPause]
G106 P0
G109 PB{2000-wrap} PLT G103 PF{799+wrap} PF{798+wrap} PX {if offsets[1]!=0, G105 PX{offsets[1]}, otherwise nothing} (Top A corner - foot end)
G103 PF{799+wrap} PF{798+wrap} PY G105 PY-{yPullIn}
G103 PF{799+wrap} PF{798+wrap} G105 PX{yPullIn*3} [this line only if nearComb(799+wrap)]
G109 PF{799+wrap} PRB G103 PF{1601-wrap} PF{1600-wrap} PXY {if offsets[2]!=0, G105 PY{offsets[2]}, otherwise nothing} G102 G108 ( BOARD GAP ) (Foot A corner)
G106 P0
G106 P1 [this line only if transferpause]
G106 P3
G109 PF{1600-wrap} PBL G103 PB{1199+wrap} PB{1200+wrap} PY {if offsets[3]!=0, G105 PY{offsets[3]}, otherwise nothing} (Foot B corner)
G103 PB{1199+wrap} PB{1200+wrap} PX G105 PX-{xPullIn}
G109 PB{1199+wrap} PTR G103 PB{1200-wrap} PB{1199-wrap} PXY {if offsets[4]!=0, G105 PX{offsets[4]}, otherwise nothing} G102 G108 (Bottom B corner - foot end)
G106 P3
G106 P2 [This line only if transferPause]
G106 P0
G109 PB{1200-wrap} PBR G103 PF{1598+wrap} PF{1599+wrap} PX {if offsets[5]!=0, G105 PX{offsets[5]}, otherwise nothing} (Bottom A corner - foot end)
G103 PF{1598+wrap} PF{1599+wrap} PY G105 PY{yPullIn} ( BOARD GAP )
G109 PF{1599+wrap} PLT G103 PF{800-wrap} PF{799-wrap} PXY {if offsets[6]!=0, G105 PX{offsets[6]}, otherwise nothing} G102 G108 (Top A corner - head end)
G106 P0
G106 P1 [this line only if transferpause]
G106 P3
G109 PF{800-wrap} PRT G103 PB{1998+wrap} PB{1999+wrap} PX {if offsets[7]!=0, G105 PX{offsets[7]}, otherwise nothing} (Top B corner - head end)
G103 PB{1998+wrap} PB{1999+wrap} PY G105 PY-{yPullIn}
G103 PB{1998+wrap} PB{1999+wrap} PY G105 PX-{yPullIn*3} [this line only if nearComb(1999+wrap)]
N35 (1, 32) (HEAD RESTART) F800 G109 PB{1999+wrap} PLB G103 PB{401-wrap} PB{400-wrap} PXY {if offsets[8]!=0, G105 PY{offsets[8]}, otherwise nothing} G102 G108 ( BOARD GAP )
G106 P3
G106 P2 [This line only if transferPause]
G106 P0
G109 PB{400-wrap} PBR G103 PF{wrap} PF{wrap+1} PY {if offsets[9]!=0, G105 PY{offsets[9]}, otherwise nothing} (Head A corner)
G103 PF{wrap} PF{wrap+1} PX G105 PX{xPullIn}
G109 PF{wrap} PTL G103 PF{2399-wrap} PF{2398-wrap} PXY {if offsets[10]!=0, G105 PX{offsets[10]}, otherwise nothing} G102 G108 (Bottom A corner - head end)
G106 P0
G106 P1 [this line only if transferpause]
G106 P3
G109 PF{2399-wrap} PBL G103 PB{399+wrap} PB{400+wrap} {if offsets[11]!=0, G105 PX{offsets[11]}, otherwise nothing} PX12 (Bottom B corner - head end)
G103 PB{399+wrap} PB{400+wrap} PY G105 PY{yPullIn}
G103 PB{399+wrap} PB{400+wrap} PX G105 PX{yPullIn*3} [this line only if nearComb(399+wrap)]

Wrap 400 is the same but it ends at Top B corner and instead of the last lines, these:
G103 PB2398 PB2399 PY G105 PY0 G111
X440 Y2315 F300
G106 P0
X440 Y2335
X650 Y2335 G111
X440 Y2335
