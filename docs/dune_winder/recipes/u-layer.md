# U Layer Recipe Description

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

Whenever we have a PB{n} or PF{n} n should wrap around after 2401 back to 1, and vice versa.

( U Layer )
N0 X7174 Y60 F300 (load new calibration file)
N1 F300 G106 P3
N2 (0, ) F300 G103 PB1201 PB1200 PXY G105 PX-50

Then for wrap n in 1-400 inclusive concatenated

(------------------STARTING LOOP {n}------------------)
G109 PB{1200+wrap} PRT G103 PB{2002-wrap} PB{2003-wrap} PXY {if offsets[0]!=0, G105 PX{offsets[0]}, otherwise nothing} G102 G108 (Top B corner - foot end)
G106 P3
G106 P2 [This line only if transferPause]
G106 P0
G109 PB{1200+wrap} PLT G103 PB{2002-wrap} PB{2003-wrap} PX {if offsets[1]!=0, G105 PX{12+offsets[1]}, otherwise nothing} (Top A corner - foot end)
G103 PF{800+wrap} PF{801+wrap} PY G105 PY-{yPullIn}
G103 PF{800+wrap} PF{801+wrap} G105 PX{yPullIn*3} [this line only if nearComb(799+wrap)]
G109 PF{799+wrap} PRB G103 PF{1601-wrap} PF{1600-wrap} PXY {if offsets[2]!=0, G105 PY{offsets[2]}, otherwise nothing} G102 G108 (bottom A corner - head end)
G106 P0
G106 P1 [this line only if transferpause]
G106 P3
G109 PF{2402-wrap} PBL G103 PB{400+wrap} PB{401+wrap} PXY {if offsets[3]!=0, G105 PY{offsets[3]}, otherwise nothing} (bottom B corner - head end, rewind)
G103 PB{400+wrap} PB{401+wrap} PX G105 PY{yPullIn}
(HEAD RESTART) G109 PB{400+wrap} PLT G103 PB{401-wrap} PB{400-wrap} PXY {if offsets[4]!=0, G105 PY{offsets[4]}, otherwise nothing} G102 G108 (head B corner)
G106 P3
G106 P2 [This line only if transferPause]
G106 P0
G109 PB{401-wrap} PLT G103 PF{0+wrap} PF{2400+wrap} PXY {if offsets[5]!=0, G105 PY{offsets[5]}, otherwise nothing} (head A corner, rewind)
G103 PF{1+wrap} PF{0+wrap} PY G105 PX{xPullIn} ( BOARD GAP )
G109 PF{1+wrap} PLT G103 PF{800-wrap} PF{799-wrap} PXY {if offsets[6]!=0, G105 PX{offsets[6]}, otherwise nothing} G102 G108 (Top A corner - head end)
G106 P0
G106 P1 [this line only if transferpause]
G106 P3
G109 PF{800-wrap} PRT G103 PB{2002+wrap} PB{2003+wrap} PX {if offsets[7]!=0, G105 PX{offsets[7]-12}, otherwise nothing} (Top B corner - head end)
G103 PB{2002+wrap} PB{2003+wrap} PY G105 PY-{yPullIn}
G103 PB{2002+wrap} PB{2003+wrap} PY G105 PX{yPullIn*3} [this line only if nearComb(1999+wrap)]
G109 PB{2001+wrap} PLB G103 PB{1201-wrap} PB{1202-wrap} PXY {if offsets[8]!=0, G105 PY{offsets[8]}, otherwise nothing} G102 G108 (bottom B corner - foot end)
G106 P3
G106 P2 [This line only if transferPause]
G106 P0
G109 PB{400-wrap} PBR G103 PF{wrap} PF{wrap+1} PY {if offsets[9]!=0, G105 PY{offsets[9]}, otherwise nothing} (bottom A corner - foot end, rewind)
G103 PF{1601+wrap} PF{1602+1} PY G105 PX{xPullIn}
G103 PF{1601+wrap} PF{1602+wrap} PX G105 PX{xPullIn*3}
G109 PF{wrap} PTL G103 PF{1601-wrap} PF{1600-wrap} PXY {if offsets[10]!=0, G105 PY{offsets[10]}, otherwise nothing} G102 G108 (foot A corner)
G106 P0
G106 P1 [this line only if transferpause]
G106 P3
G109 PF{1601-wrap} PBL G103 PB{1201+wrap} PB{1200+wrap} {if offsets[11]!=0, G105 PY{offsets[11]}, otherwise nothing} PX12 (foot b corner, rewind)
G103 PB{1201+wrap} PB{1200+wrap} PY G105 PX-{xPullIn}



"emit (------------------STARTING LOOP ${wrap}------------------)",
PB${1200 + wrap} PBR PB${2002 - wrap} PB${2003 - wrap} (top b foot end)
PB${1200 + wrap} PLT PB${2002 - wrap} PB${2003 - wrap} (top a foot end)
G103 PF${800 + wrap} PF${801 + wrap}
"if near_comb(799 + wrap): X+
PF${800 + wrap} PLB PF${2402 - wrap} PF${2403 - wrap} (Bottom A corner - head end)",
PF${2402 - wrap} PBR PB${400 + wrap} PB${401 + wrap} (Bottom B corner - head end, rewind)",
PB${400 + wrap} PB${401 + wrap}
PB${400 + wrap} PLT PB${401 - wrap} PB${400 - wrap} (Head B corner)",
PB${401 - wrap} PLT PF${wrap} PF${2400 + wrap} (Head A corner, rewind)",
PF${1 + wrap} PF${wrap}
PF${1 + wrap} PRT PF${800 - wrap} PF${799 - wrap} (Top A corner - head end)",
PF${800 - wrap} PRT PB${2002 + wrap} PB${2003 + wrap} (Top B corner - head end)",
PB${2002 + wrap} PB${2003 + wrap}
"if near_comb(1999 + wrap): x+
PB${2001 + wrap} PRB PB${1201 - wrap} PB${1202 - wrap} (Bottom B corner - foot end)",
PB${1199 + wrap} PBL PF${1601 + wrap} PF${1602 + wrap} (Bottom A corner - foot end, rewind)",
PF${1601 + wrap} PF${1602 + wrap}
"if near_comb(1601 + wrap): emit G113 PTOLERANT G103 PF${1601 + wrap} PF${1602 + wrap} PX G105 ${coord('PX', X_PULL_IN * COMB_PULL_FACTOR)}",
"emit G113 PPRECISE G109 PF${1601 + wrap} PRT G103 PF${1601 - wrap} PF${1600 - wrap} PXY ${offset('PY', offsets[10])} G102 G108 (Foot A corner)",
"transfer a_to_b_transfer",
"emit G113 PPRECISE G109 PF${1601 - wrap} PRT G103 PB${1201 + wrap} PB${1200 + wrap} PXY ${offset('PY', offsets[11])} (Foot B corner, rewind)",
"emit G113 PTOLERANT G103 PB${1201 + wrap} PB${1200 + wrap} PX G105 ${coord('PX', -X_PULL_IN)}",
