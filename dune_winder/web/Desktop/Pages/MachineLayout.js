function MachineLayout(modules) {
  var page = modules.get("Page");
  page.loadSubPage(
    "/Desktop/Modules/PositionGraphic",
    "#positionGraphicDiv",
    function () {
      var positionGraphic = modules.get("PositionGraphic");
      if (positionGraphic) {
        positionGraphic.initialize();
      }
    },
  );
}