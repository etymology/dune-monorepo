function Grid(modules) {
  var page = modules.get("Page");
  var winder = modules.get("Winder");

  page.loadSubPage(
    "/Desktop/Modules/PositionGraphic",
    "#positionGraphicDiv",
    function () {
      var positionGraphic = modules.get("PositionGraphic");
      positionGraphic.initialize();
    },
  );

  page.loadSubPage("/Desktop/Modules/MotorStatus", "#motorStatusDiv");

  page.loadSubPage("/Desktop/Modules/G_Code", "#gCodeDiv", function () {
    var gCode = modules.get("G_Code");
    gCode.create(3);
  });

  page.loadSubPage("/Desktop/Modules/RecentLog", "#recentLogDiv", function () {
    var recentLog = modules.get("RecentLog");
    recentLog.create(100);
  });
}
