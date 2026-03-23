function ManualMove(modules) {
  var self = this;

  var page = modules.get("Page");
  var winder = modules.get("Winder");
  var commands = window.CommandCatalog;
  var sliders = null;
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
    winder.batch(
      [
        { id: "maxVelocity", name: commands.process.maxVelocity, args: {} },
        { id: "velocityScale", name: commands.process.getGCodeVelocityScale, args: {} },
      ],
      function (response) {
        if (!response || !response.ok || !response.data || !response.data.results) {
          return;
        }

        var maxVelocityResult = response.data.results.maxVelocity;
        var velocityScaleResult = response.data.results.velocityScale;
        if (!maxVelocityResult || !maxVelocityResult.ok) {
          return;
        }

        var maxVelocity = parseFloat(maxVelocityResult.data);
        if (!isFinite(maxVelocity) || maxVelocity <= 0) {
          return;
        }

        var velocityScale = 1.0;
        if (velocityScaleResult && velocityScaleResult.ok) {
          velocityScale = parseFloat(velocityScaleResult.data);
          if (!isFinite(velocityScale) || velocityScale <= 0) {
            velocityScale = 1.0;
          }
        }

        incrementalJogVelocity = maxVelocity * velocityScale;
      },
    );
  };

  var setStatus = function (text) {
    $("#manualMoveStatus").text(text);
  };

  var handleGCodeExecutionResponse = function (response) {
    if (response && response.ok) {
      setStatus("Executed with no errors.");
      return;
    }

    if (response && response.error && response.error.message) {
      setStatus("Error interpreting line: " + response.error.message);
      return;
    }

    setStatus("Manual G-code execution failed.");
  };

  var executeActionGCode = function (gCode) {
    setStatus("Request G-Code execution...");
    winder.call(
      commands.process.executeGCodeLine,
      { line: gCode },
      function (response) {
        handleGCodeExecutionResponse(response);
      },
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

    winder.call(
      commands.process.executeGCodeLine,
      { line: gCode },
      function (response) {
        handleGCodeExecutionResponse(response);
      },
    );
  };

  this.reset = function () {
    winder.call(commands.process.acknowledgeError, {});
  };

  this.latch = function () {
    winder.call(commands.io.moveLatch, {});
  };

  this.servoDisable = function () {
    winder.call(commands.process.servoDisable, {});
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

  page.loadSubPage("/Desktop/Modules/Sliders", "#slidersDiv", function () {
    sliders = modules.get("Sliders");
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
