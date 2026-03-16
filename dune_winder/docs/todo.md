# todo
- implement grafana database for monitoring tags
- consider how to improve latency of tag reads by reading several at once
- track wrap number and wire number with tension 
- make g code reversible so able to unwind as well as wind
zx plane movements then zy plane movements and finally full xyz movements protected from collision
- implement transpiler to plc ladder logic
- change the way anchored wire pulls are calculated to make gcode more transparent. Should the wire pull be stateful, as in it memorizes the physical state of which pin we're wrapped around and take only a target, or should it take the
