function ManualMovePopup(modules) {
  var page = modules.get("Page");
  var popupContext = getParameterByName("context") || "apa";

  document.title = "Manual Move - Chicago Winder Interface";

  page.loadSubPage("/Desktop/Modules/FullStop", "#manualMovePopupStop");

  page.loadSubPage("/Desktop/Modules/ManualMove", "#manualMovePopupContent", function () {
    var manualMove = modules.get("ManualMove");
    var popupOptions = {
      context: popupContext,
      hidePopout: true,
    };

    if ("calibrate" == popupContext) {
      popupOptions.velocityCallback = function () {
        return 1000;
      };
      popupOptions.enablePositionCopy = true;
    }

    manualMove.configure(popupOptions);
  });
}
