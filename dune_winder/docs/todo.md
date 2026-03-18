# todo
- implement grafana database for monitoring tags
- consider how to improve latency of tag reads by reading several at once
- track wrap number and wire number with tension 
- make g code reversible so able to unwind as well as wind
zx plane movements then zy plane movements and finally full xyz movements protected from collision
- implement transpiler to plc ladder logic
- change the way anchored wire pulls are calculated to make gcode more transparent. Should the wire pull be stateful, as in it memorizes the physical state of which pin we're wrapped around and take only a target, or should it take the
- There's currently a problem with the queued motion execution in the G-layer where the motion seems to move far beyond the target or not move at all. To debug this, we should display the waypoints and arcs of the motion planner on a graphic similar to that in the position graphic of the web server, superimposed upon an image of the APA except we don't need to show any of the graphics except for the APA itself. 


Gcode requirements: 