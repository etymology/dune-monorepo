function ManualMove(modules) {
  var self = this;

  var page = modules.get("Page");
  var winder = modules.get("Winder");
  var sliders = modules.get("Sliders");
  var incrementalJog = null;
  var isMotorStatusLoaded = false;
  var isPositionCopyEnabled = false;
  var didInitializePositionCopy = false;
  var popupContext = "apa";
  var popupWindow = null;
  var incrementalJogVelocity = 10.0;
  var velocityCallback = null;
  var isPopupMode = "1" == getParameterByName("popup");
  var POPUP_CONFIG = {
    width: 780,
    height: 640,
  };

  var buildPopoutFeatures = function (config) {
    var screenLeft =
      window.screenLeft !== undefined ? window.screenLeft : window.screenX;
    var screenTop =
      window.screenTop !== undefined ? window.screenTop : window.screenY;
    var left =
      screenLeft + Math.max(40, Math.round((window.outerWidth - config.width) / 2));
    var top =
      screenTop + Math.max(40, Math.round((window.outerHeight - config.height) / 2));

    return [
      "popup=yes",
      "resizable=yes",
      "scrollbars=yes",
      "width=" + config.width,
      "height=" + config.height,
      "left=" + left,
      "top=" + top,
    ].join(",");
  };

  var initializePositionCopy = function () {
    if (!isPositionCopyEnabled || didInitializePositionCopy || !isMotorStatusLoaded) {
      return;
    }

    didInitializePositionCopy = true;
    new CopyField("#xPosition", "#xPositionCell");
    new CopyField("#yPosition", "#yPositionCell");
    new CopyField("#zPosition", "#zPositionCell");
  };

  var readDefaultVelocity = function () {
    if (
      sliders &&
      sliders.getVelocity &&
      document.getElementById("velocitySlider")
    ) {
      return sliders.getVelocity();
    }

    return incrementalJogVelocity;
  };

  var applyVelocityCallback = function () {
    if (!incrementalJog) {
      return;
    }

    incrementalJog.velocityCallback(function () {
      if (velocityCallback) {
        return velocityCallback();
      }

      return readDefaultVelocity();
    });
  };

  var refreshIncrementalJogVelocity = function () {
    winder.remoteAction("process.maxVelocity()", function (maxVelocity) {
      maxVelocity = parseFloat(maxVelocity);
      if (!isFinite(maxVelocity) || maxVelocity <= 0) {
        return;
      }

      winder.remoteAction(
        "process.gCodeHandler.getVelocityScale()",
        function (velocityScale) {
          velocityScale = parseFloat(velocityScale);
          if (!isFinite(velocityScale) || velocityScale <= 0) {
            velocityScale = 1.0;
          }
          incrementalJogVelocity = maxVelocity * velocityScale;
        },
      );
    });
  };

  var setStatus = function (text) {
    $("#manualMoveStatus").text(text);
  };

  var executeActionGCode = function (gCode) {
    winder.remoteAction(
      "process.executeG_CodeLine( " + JSON.stringify(gCode) + " )",
    );
  };

  this.configure = function (options) {
    options = options || {};

    if (options.context) {
      popupContext = options.context;
    }

    if (options.velocityCallback) {
      velocityCallback = options.velocityCallback;
    }

    if (options.enablePositionCopy) {
      isPositionCopyEnabled = true;
    }

    if (options.hidePopout) {
      $("#manualMovePopoutButton").hide();
    }

    initializePositionCopy();
    applyVelocityCallback();

    return this;
  };

  this.refreshDefaultVelocity = function () {
    refreshIncrementalJogVelocity();
  };

  this.openPopout = function () {
    if (isPopupMode) {
      return;
    }

    if (popupWindow && !popupWindow.closed) {
      popupWindow.focus();
      return;
    }

    popupWindow = window.open(
      "/Desktop/index.html?page=ManualMovePopup&popup=1&context=" +
        encodeURIComponent(popupContext),
      "manualMovePanel_" + popupContext,
      buildPopoutFeatures(POPUP_CONFIG),
    );

    if (!popupWindow) {
      alert("Allow pop-up windows to open the Manual Move panel.");
      return;
    }

    popupWindow.focus();
  };

  this.executeGCode = function () {
    var gCode = $.trim($("#manualGCode").val()).toUpperCase();
    if ("" === gCode) {
      setStatus("Enter a manual G-code line first.");
      return;
    }

    $("#manualGCode").val(gCode);
    setStatus("Request G-Code execution...");

    winder.remoteAction(
      "process.executeG_CodeLine( " + JSON.stringify(gCode) + " )",
      function (data) {
        if (!data || (typeof data == "object" && data.ok !== false)) {
          setStatus("Executed with no errors.");
          return;
        }

        if (typeof data == "string") {
          setStatus("Error interpreting line: " + data);
          return;
        }

        setStatus(data.error || "Manual G-code execution failed.");
      },
    );
  };

  this.reset = function () {
    winder.remoteAction("process.acknowledgeError()");
  };

  this.latch = function () {
    winder.remoteAction("io.plcLogic.move_latch()");
  };

  this.servoDisable = function () {
    winder.remoteAction("process.servoDisable()");
  };

  refreshIncrementalJogVelocity();
  winder.addErrorClearCallback(refreshIncrementalJogVelocity);

  page.loadSubPage("/Desktop/Modules/MotorStatus", "#motorStatusDiv", function () {
    isMotorStatusLoaded = true;
    initializePositionCopy();
  });

  page.loadSubPage("/Desktop/Modules/IncrementalJog", "#increments", function () {
    incrementalJog = modules.get("IncrementalJog");
    applyVelocityCallback();
  });

  $("#manualMovePopoutButton").click(function () {
    self.openPopout();
  });

  $("#manualGCodeButton").click(function () {
    self.executeGCode();
  });

  $("#manualGCode").on("input", function () {
    this.value = this.value.toUpperCase();
  });

  $("#manualMoveResetButton").click(function () {
    self.reset();
  });

  $("#manualMoveLatchButton").click(function () {
    self.latch();
  });

  $("#manualMoveServoDisableButton").click(function () {
    self.servoDisable();
  });

  $("[data-manual-gcode]").click(function () {
    executeActionGCode($(this).attr("data-manual-gcode"));
  });

  if (isPopupMode) {
    $("#manualMovePopoutButton").hide();
  }

  window["manualMove"] = this;
}
