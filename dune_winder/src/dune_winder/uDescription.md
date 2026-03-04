# recipe description

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