function APA(modules) {
  var self = this;

  // True when the APA settings can be modified.  Used to prevent modifications
  // to the APA while the machine is running.
  var apaEnabled = true;

  // True when
  var apaEnabledInhabit = false;

  var gCodeLine = {};

  var G_CODE_ROWS = 14;

  var LOG_ENTIRES = 6;

  // Tags to disable during APA loading.
  var apaInterfaceTags = [
    "#layerSelection",
    "#gCodeSelection",
    "#openGCodeButton",
    "#openCalibrationButton",
    "#apaStageSelect",
    "#apaStageReason",
    "#apaStageButton",
  ];

  var stage = null;
  var isStopping = false;
  var forecastPeriodRequestId = 0;
  var forecastPeriodHandledId = 0;
  var forecastLogRequestId = 0;
  var forecastLogHandledId = 0;
  var forecastPollTimer = null;

  //-----------------------------------------------------------------------------
  // Uses:
  //   Enable all APA interface controls.
  //-----------------------------------------------------------------------------
  this.enableAPA_Interface = function () {
    apaEnabled = true;
    for (var index in apaInterfaceTags) {
      var tag = apaInterfaceTags[index];
      $(tag).prop("disabled", false);
    }

    $("#loading").html("&nbsp;");
    this.populateLists();
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Disable all APA interface controls.
  //-----------------------------------------------------------------------------
  this.disableAPA_Interface = function (message) {
    apaEnabled = false;
    $("#loading").html(message);

    for (var index in apaInterfaceTags) {
      var tag = apaInterfaceTags[index];
      $(tag).prop("disabled", true);
    }
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start/stop recipe execution.
  // Input:
  //   isRunning - True to start, false to stop.
  //-----------------------------------------------------------------------------
  this.setRunningState = function (isRunning) {
    if (isRunning) winder.remoteAction("process.start()");
    else winder.remoteAction("process.stop()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Execute next line of G-Code, then stop.
  //-----------------------------------------------------------------------------
  this.stepG_Code = function () {
    winder.remoteAction("process.step()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Re-enable APA interface.  Callback function.
  //-----------------------------------------------------------------------------
  this.reenableAPA = function () {
    self.enableAPA_Interface();
    apaEnabledInhabit = false;
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   G-Code selection callback.
  //-----------------------------------------------------------------------------
  this.selectG_Code = function () {
    // Get the layer and G-Code recipe.
    var layer = $("#layerSelection").val();
    var gCodeSelection = $("#gCodeSelection").val();

    // If the filename starts with a layer letter followed by a hyphen (e.g.
    // "U-layer.gc", "X-layer.gc"), auto-update the layer selection to match.
    var layerMatch = gCodeSelection.match(/^([GUVX])-/i);
    if (layerMatch) {
      layer = layerMatch[1].toUpperCase();
      $("#layerSelection").val(layer);
    }

    // If not the null selection...
    if ("" != gCodeSelection) {
      // Invalidate any pending forecast fetches while switching recipes.
      forecastPeriodRequestId += 1;
      forecastPeriodHandledId = forecastPeriodRequestId;
      forecastLogRequestId += 1;
      forecastLogHandledId = forecastLogRequestId;
      forecastRecipePeriod = null;
      forecastRecentRows = null;
      if ("function" === typeof updateForecast) updateForecast();

      // Disable APA interface during loading process.
      apaEnabledInhabit = true;
      this.disableAPA_Interface("Loading G-Code");

      // Begin loading G-Code.
      winder.remoteAction(
        'process.apa.loadRecipe( "' +
          layer +
          '", "' +
          gCodeSelection +
          '", -1 )',
        self.reenableAPA,
      );
    }
  };

  this.selectLayer = function () {
    // Get the selected layer and build default layer recipe name.
    var layer = $("#layerSelection").val();
    var defaultRecipe = (layer + "-layer.gc").toLowerCase();

    // Try to find the layer recipe in the available recipe list.
    winder.remoteAction("process.getRecipes()", function (recipes) {
      var matchedRecipe = "";

      for (var i = 0; recipes && i < recipes.length; i += 1) {
        if (recipes[i].toLowerCase() === defaultRecipe) {
          matchedRecipe = recipes[i];
          break;
        }
      }

      // Only load a new recipe when a matching layer file exists.
      if (matchedRecipe) {
        $("#gCodeSelection").val(matchedRecipe);
        self.selectG_Code();
      }
    });
  };

  this.openG_Code = function () {
    var gCodeSelection = $("#gCodeSelection").val();
    winder.remoteAction(
      "process.openRecipeInEditor(" + JSON.stringify(gCodeSelection) + ")",
    );
  };

  this.openCalibration = function () {
    winder.remoteAction("process.openCalibrationInEditor()");
  };

  function refreshRecipePeriod() {
    forecastPeriodRequestId += 1;
    var requestId = forecastPeriodRequestId;
    winder.remoteAction("process.getRecipePeriod()", function (data) {
      if (requestId < forecastPeriodHandledId) return;
      forecastPeriodHandledId = requestId;
      forecastRecipePeriod = data;
      if ("function" === typeof updateForecast) updateForecast();
    });
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load values for and repopulate all lists.
  //-----------------------------------------------------------------------------
  this.populateLists = function () {
    winder.populateComboBox(
      "#gCodeSelection",
      "process.getRecipes()",
      "process.getRecipeName()",
    );

    // Get the current layer.
    winder.remoteAction("process.getRecipeLayer()", function (data) {
      $("#layerSelection").val(data);
    });

    refreshRecipePeriod();
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to advance G-Code by one line.
  //-----------------------------------------------------------------------------
  this.nextLine = function () {
    if (null != gCodeLine["currentLine"]) {
      // Next line is the current line because the current line has been incremented
      // by 1.
      var nextLine = gCodeLine["currentLine"];
      if (nextLine < gCodeLine["totalLines"] - 1)
        winder.remoteAction("process.setG_CodeLine( " + nextLine + " )");
    }
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to retard G-Code by one line.
  //-----------------------------------------------------------------------------
  this.previousLine = function () {
    if (null != gCodeLine["currentLine"]) {
      var nextLine = gCodeLine["currentLine"] - 2;
      if (nextLine >= -1)
        winder.remoteAction("process.setG_CodeLine( " + nextLine + " )");
    }
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for setting next active G-Code line.
  //-----------------------------------------------------------------------------
  this.gotoLine = function () {
    var line = parseInt($("#apaLine").val()) - 2;
    winder.remoteAction("process.setG_CodeLine( " + line + " )");
  };

  this.gotoWrap = function () {
    var wrap = parseInt($("#wrapNumber").val(), 10);
    if (!isFinite(wrap) || wrap < 1) return;

    winder.remoteAction(
      "process.getWrapSeekLine( " + wrap + " )",
      function (line) {
        if (null === line || undefined === line) return;
        winder.remoteAction("process.setG_CodeLine( " + line + " )");
      },
    );
  };

  this.refreshGCode = function () {
    // Get the layer and G-Code recipe.
    var layer = $("#layerSelection").val();
    var gCodeSelection = $("#gCodeSelection").val();
    var currentLine = gCodeLine["currentLine"] - 1;
    winder.remoteAction(
      'process.apa.loadRecipe( "' +
        layer +
        '", "' +
        gCodeSelection +
        '", ' +
        currentLine +
        " )",
      self.reenableAPA,
    );
  };
  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for setting G-Code breakpoint.
  //-----------------------------------------------------------------------------
  this.runToLine = function () {
    winder.remoteAction(
      "process.setG_CodeRunToLine( " + $("#apaBreakLine").val() + " )",
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for setting spool wire amount.
  //-----------------------------------------------------------------------------
  this.setSpool = function () {
    // Get the values and convert to millimeters.
    var value = $("#setSpool").val() * 1000;
    winder.remoteAction("process.spool.setWire( " + value + " )");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Change the APA stage of progress.
  //-----------------------------------------------------------------------------
  this.changeStage = function () {
    var newStage = $("#apaStageSelect").val();
    var reasonForChange = $("#apaStageReason").val();
    winder.remoteAction(
      "process.setStage( " + newStage + ', "' + reasonForChange + '" )',
      function () {
        $("#apaStageReason").val("");
        self.populateLists();
      },
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Stop wind after completing current move.
  //-----------------------------------------------------------------------------
  this.stopNext = function () {
    winder.remoteAction("process.stopNextLine()", function () {
      isStopping = true;
    });
  };
  var page = modules.get("Page");
  var winder = modules.get("Winder");
  var runStatus = modules.get("RunStatus");

  // Populate lists and have this function run after error recovery.
  this.populateLists();
  winder.addErrorClearCallback(this.populateLists);

  // Set updates of current line and total lines.
  winder.addPeriodicCallback("process.gCodeHandler.getLine()", function (data) {
    if (null !== data) {
      data = data + 1;
      gCodeLine["currentLine"] = data;
    } else {
      data = "-";
      gCodeLine["currentLine"] = null;
    }

    $("#currentLine").text(data);
  });

  winder.addPeriodicDisplay(
    "process.gCodeHandler.getTotalLines()",
    "#totalLines",
    gCodeLine,
    "totalLines",
  );

  // Special periodic for current APA stage.
  winder.addPeriodicCallback("process.getStage()", function (value) {
    var STAGES = [
      "Uninitialized",
      "X first",
      "X second",
      "V first",
      "V second",
      "U first",
      "U second",
      "G first",
      "G second",
      "Sign off",
      "Complete",
    ];

    // If there is no APA loaded, the value will be an empty string and
    // the options to change the stage need to be disabled.
    var isDisabled = false;
    if ("" === value) {
      stage = "(no APA loaded)";
      isDisabled = true;
    }
    // Translate the stage name.
    else stage = STAGES[value];

    // Enable/disable APA stage control interface.
    $("#apaStageSelect").prop("disabled", isDisabled);
    $("#apaStageReason").prop("disabled", isDisabled);
    $("#apaStageButton").prop("disabled", isDisabled);

    // Display the current stage.
    $("#apaStage").html(stage);
  });

  page.loadSubPage(
    "/Desktop/Modules/PositionGraphic",
    "#positionGraphicDiv",
    function () {
      console.log("PositionGraphic module loaded.");
      var positionGraphic = modules.get("PositionGraphic");
      if (positionGraphic) {
        console.log("Initializing PositionGraphic...");
        positionGraphic.initialize();
      } else {
        console.error("PositionGraphic module not found!");
      }
    },
  );

  page.loadSubPage(
    "/Desktop/Modules/ManualMove",
    "#manualMoveCard",
    function () {
      var manualMove = modules.get("ManualMove");
      manualMove.configure({
        context: "apa",
      });
    },
  );

  // Callback run after period updates happen to enable/disable APA controls
  // depending on machine state.
  winder.addPeriodicEndCallback(function () {
    // Display control state.
    var controlState = runStatus.states["controlState"];
    $("#controlState").text(controlState);

    // Start button enable.
    var startDisable = "StopMode" != controlState || apaEnabledInhabit;
    $("#startButton").prop("disabled", startDisable);
    $("#stepButton").prop("disabled", startDisable);

    // Stop button enable.
    var stopDisable = "WindMode" != controlState;
    $("#stopButton").prop("disabled", stopDisable | isStopping);

    // If the winder was stopped and is now running disable APA controls.
    if (!stopDisable && apaEnabled && !apaEnabledInhabit) {
      self.disableAPA_Interface("Running.");
    }
    // If the winder was running but is now stopped enable APA controls.
    else if (stopDisable && !apaEnabled && !apaEnabledInhabit) {
      self.enableAPA_Interface();
      isStopping = false;
    }
  });

  page.loadSubPage("/Desktop/Modules/G_Code", "#gCodeDiv", function () {
    var gCode = modules.get("G_Code");
    gCode.create(G_CODE_ROWS);
  });

  page.loadSubPage("/Desktop/Modules/RecentLog", "#recentLogDiv", function () {
    var recentLog = modules.get("RecentLog");
    recentLog.create(LOG_ENTIRES);
  });

  createSlider = function (slider, getString, setString) {
    var isLoad = true;
    velocitySliderFunction = function (event, ui) {
      $("#" + slider + "Value").html(ui.value + "%");
    };

    $("#" + slider + "Slider").slider({
      min: 5,
      max: 100,
      value: 100,
      step: 5,

      change: function (event, ui) {
        if (!isLoad) {
          var value = ui.value / 100.0;
          winder.remoteAction(setString + "( " + value + " )");
          var manualMove = modules.get("ManualMove");
          if (manualMove && manualMove.refreshDefaultVelocity) {
            manualMove.refreshDefaultVelocity();
          }
        }
        velocitySliderFunction(event, ui);
        isLoad = false;
      },

      slide: velocitySliderFunction,
    });

    var readSlider = function () {
      winder.remoteAction(getString + "()", function (value) {
        if (value) {
          isLoad = true;
          value *= 100;
          $("#" + slider + "Slider").slider("value", value);
        }
      });
    };

    readSlider();
    // winder.addErrorClearCallback
    // (
    //   function()
    //   {
    //     createSlider
    //     (
    //       "velocity",
    //       "process.gCodeHandler.getVelocityScale",
    //       "process.setG_CodeVelocityScale"
    //     )
    //
    //     readSlider()
    //   }
    // )
  };

  var createSliders = function () {
    createSlider(
      "velocity",
      "process.gCodeHandler.getVelocityScale",
      "process.setG_CodeVelocityScale",
    );

    //createSlider( "acceleration" )
    //createSlider( "deceleration" )
  };

  createSliders();
  winder.addErrorClearCallback(createSliders);

  // Forecast refresh: compute in-browser using the same log stream as RecentLog.
  var forecastRecentRows = null;
  var forecastRecipePeriod = null;
  var FORECAST_LAYER_CONFIG = {
    X: { wrap: 480, offset: -1 },
    G: { wrap: 481, offset: -1 },
    U: { wrap: 400, offset: 27 },
    V: { wrap: 400, offset: 11 },
  };

  var _isIntegerText = function (text) {
    return /^-?\d+$/.test(text);
  };

  var _fitLinear = function (x, y) {
    var n = x.length;
    if (n < 2) return null;
    var sx = 0;
    var sy = 0;
    var sxy = 0;
    var sxx = 0;
    for (var i = 0; i < n; i += 1) {
      sx += x[i];
      sy += y[i];
      sxy += x[i] * y[i];
      sxx += x[i] * x[i];
    }
    var denom = n * sxx - sx * sx;
    if (denom === 0) return null;
    return {
      a: (n * sxy - sx * sy) / denom,
      b: (sy - ((n * sxy - sx * sy) / denom) * sx) / n,
    };
  };

  var _mod = function (value, period) {
    return ((value % period) + period) % period;
  };

  var _interpolateSeconds = function (numbers, seconds, target) {
    for (var i = 0; i < numbers.length - 1; i += 1) {
      if (target >= numbers[i] && target <= numbers[i + 1]) {
        var dx = numbers[i + 1] - numbers[i];
        if (dx === 0) return seconds[i];
        var frac = (target - numbers[i]) / dx;
        return seconds[i] + frac * (seconds[i + 1] - seconds[i]);
      }
    }
    return null;
  };

  var _buildSeasonalModels = function (numbers, seconds, period) {
    var phaseBuckets = {};
    for (var i = 0; i < numbers.length; i += 1) {
      var lineNumber = Math.round(numbers[i]);
      var phase = _mod(lineNumber, period);
      var cycle = Math.floor(lineNumber / period);

      if (!phaseBuckets[phase]) {
        phaseBuckets[phase] = [];
      }
      phaseBuckets[phase].push({
        cycle: cycle,
        seconds: seconds[i],
      });
    }

    var models = {};
    for (var phaseKey in phaseBuckets) {
      var entries = phaseBuckets[phaseKey];
      entries.sort(function (a, b) {
        return a.cycle - b.cycle;
      });

      var seenCycle = {};
      var cycles = [];
      var phaseSeconds = [];
      for (var j = 0; j < entries.length; j += 1) {
        var cycleValue = entries[j].cycle;
        if (seenCycle[cycleValue]) continue;
        seenCycle[cycleValue] = true;
        cycles.push(cycleValue);
        phaseSeconds.push(entries[j].seconds);
      }

      if (cycles.length < 2) continue;

      var fit = _fitLinear(cycles, phaseSeconds);
      if (!fit || !isFinite(fit.a) || !isFinite(fit.b) || fit.a <= 0) continue;

      var sumSq = 0;
      for (var k = 0; k < cycles.length; k += 1) {
        var err = phaseSeconds[k] - (fit.a * cycles[k] + fit.b);
        sumSq += err * err;
      }
      var rmse = Math.sqrt(sumSq / cycles.length);

      models[phaseKey] = {
        phase: parseInt(phaseKey, 10),
        fit: fit,
        rmse: rmse,
      };
    }

    return models;
  };

  var _predictSeasonalSeconds = function (
    numbers,
    seconds,
    targetLine,
    period,
  ) {
    // Need multiple full periods before seasonal estimates are stable.
    if (numbers.length < period + 2) return null;

    var models = _buildSeasonalModels(numbers, seconds, period);
    var modelCount = 0;
    for (var key in models) {
      if (models.hasOwnProperty(key)) modelCount += 1;
    }
    if (modelCount < 2) return null;

    var targetPhase = _mod(Math.round(targetLine), period);
    var candidate = null;

    var scoreModel = function (model) {
      var predCycle = (targetLine - model.phase) / period;
      if (!isFinite(predCycle) || predCycle < 0) return null;

      var predSeconds = model.fit.a * predCycle + model.fit.b;
      if (!isFinite(predSeconds)) return null;

      var phaseDistance = Math.abs(model.phase - targetPhase);
      phaseDistance = Math.min(phaseDistance, period - phaseDistance);

      return {
        seconds: predSeconds,
        rmse: model.rmse,
        phaseDistance: phaseDistance,
      };
    };

    // Prefer exact target phase when available.
    if (models.hasOwnProperty(targetPhase)) {
      candidate = scoreModel(models[targetPhase]);
      if (candidate) return candidate.seconds;
    }

    // Otherwise choose the phase model with best fit quality, tie-breaking by phase distance.
    for (var modelKey in models) {
      var scored = scoreModel(models[modelKey]);
      if (!scored) continue;
      if (!candidate) {
        candidate = scored;
      } else if (scored.rmse < candidate.rmse) {
        candidate = scored;
      } else if (
        scored.rmse === candidate.rmse &&
        scored.phaseDistance < candidate.phaseDistance
      ) {
        candidate = scored;
      }
    }

    if (!candidate) return null;
    return candidate.seconds;
  };

  var _getLatestWindRunPoints = function (rows) {
    var pointsRev = [];
    if (!rows) return pointsRev;

    for (var i = rows.length - 1; i >= 0; i -= 1) {
      var parts = rows[i].split("\t");
      if (parts.length < 3) continue;
      if (parts[1] !== "WindMode") continue;

      var eventType = parts[2];
      if (eventType !== "LINE" && eventType !== "WIND") continue;

      var numberText = parts[parts.length - 1];
      if (!_isIntegerText(numberText)) continue;

      var when = new Date(parts[0] + "Z");
      if (isNaN(when.getTime())) continue;

      pointsRev.push({
        number: parseInt(numberText, 10),
        seconds: when.getTime() / 1000.0,
      });

      // Start marker for this run.
      if (eventType === "WIND") break;
    }

    pointsRev.reverse();
    return pointsRev;
  };

  var _preparePoints = function (points) {
    var sorted = points.slice().sort(function (a, b) {
      return a.number - b.number;
    });

    var seen = {};
    var numbers = [];
    var seconds = [];
    for (var i = 0; i < sorted.length; i += 1) {
      var number = sorted[i].number;
      if (seen[number]) continue;
      seen[number] = true;
      numbers.push(number);
      seconds.push(sorted[i].seconds);
    }

    return {
      numbers: numbers,
      seconds: seconds,
    };
  };

  var _formatTime = function (date) {
    var pad2 = function (value) {
      return value < 10 ? "0" + value : "" + value;
    };
    return (
      pad2(date.getHours()) +
      ":" +
      pad2(date.getMinutes()) +
      ":" +
      pad2(date.getSeconds())
    );
  };

  var _formatForecastPeriod = function (recipePeriod) {
    if (!recipePeriod || recipePeriod < 1) return "";
    return " (" + recipePeriod + ")";
  };

  var _calculateForecastFromLogs = function (
    layer,
    rows,
    targetWrap,
    recipePeriod,
  ) {
    var config = FORECAST_LAYER_CONFIG[layer];
    if (!config) return null;
    if (!recipePeriod || recipePeriod < 1) return null;

    var points = _getLatestWindRunPoints(rows);
    var prepared = _preparePoints(points);
    var numbers = prepared.numbers;
    var seconds = prepared.seconds;
    var targetLine = targetWrap * recipePeriod - config.offset;

    if (numbers.length === 0) return null;

    var predictedSeconds = null;
    var predictionMethod = "last_known";
    if (numbers.length >= 2) {
      var minNumber = numbers[0];
      var maxNumber = numbers[numbers.length - 1];

      if (targetLine >= minNumber && targetLine <= maxNumber) {
        predictedSeconds = _interpolateSeconds(numbers, seconds, targetLine);
        predictionMethod = "interpolate";
      } else {
        predictedSeconds = _predictSeasonalSeconds(
          numbers,
          seconds,
          targetLine,
          recipePeriod,
        );
        if (null !== predictedSeconds) predictionMethod = "seasonal";

        if (null === predictedSeconds) {
          var fit = _fitLinear(numbers, seconds);
          if (fit) {
            predictedSeconds = fit.a * targetLine + fit.b;
            predictionMethod = "linear";
          }
        }
      }
    }

    if (null === predictedSeconds) {
      predictedSeconds = seconds[seconds.length - 1];
      predictionMethod = "last_known";
    }

    if (!isFinite(predictedSeconds)) return null;

    return {
      wrap: targetWrap,
      time: _formatTime(new Date(Math.round(predictedSeconds * 1000.0))),
      isSeasonal: predictionMethod === "seasonal",
    };
  };

  var _getForecastTargetWraps = function (layer) {
    if (layer === "X" || layer === "G") return [240, 480];
    if (layer === "U" || layer === "V") return [200, 400];
    return [];
  };

  var updateForecast = function () {
    var activeLayer = $("#layerSelection").val();
    var targetWraps = _getForecastTargetWraps(activeLayer);
    var periodSuffix = _formatForecastPeriod(forecastRecipePeriod);
    if (targetWraps.length === 0) {
      $("#forecastWrapText").text("-");
      return;
    }

    var lines = [];
    for (var i = 0; i < targetWraps.length; i += 1) {
      var forecastData = _calculateForecastFromLogs(
        activeLayer,
        forecastRecentRows,
        targetWraps[i],
        forecastRecipePeriod,
      );
      if (forecastData) {
        var forecastClass = forecastData.isSeasonal
          ? "forecastItem forecastSeasonal"
          : "forecastItem forecastFallback";
        lines.push(
          '<span class="' +
            forecastClass +
            '">Wrap ' +
            forecastData.wrap +
            " at " +
            forecastData.time +
            periodSuffix +
            "</span>",
        );
      } else {
        lines.push(
          '<span class="forecastItem forecastFallback">Wrap ' +
            targetWraps[i] +
            " at -" +
            periodSuffix +
            "</span>",
        );
      }
    }

    if (lines.length > 0) {
      $("#forecastWrapText").html(lines.join(""));
    } else {
      $("#forecastWrapText").text("-");
    }
  };

  var FORECAST_LOG_LINES = 2000;
  var fetchForecastLogs = function () {
    forecastLogRequestId += 1;
    var requestId = forecastLogRequestId;
    winder.remoteAction(
      "log.getAll( " + FORECAST_LOG_LINES + " )",
      function (data) {
        if (requestId < forecastLogHandledId) return;
        forecastLogHandledId = requestId;
        forecastRecentRows = data;
        updateForecast();
      },
    );
  };

  fetchForecastLogs();
  if (window.__apaForecastPollTimer) {
    clearInterval(window.__apaForecastPollTimer);
  }
  forecastPollTimer = setInterval(fetchForecastLogs, 2000);
  window.__apaForecastPollTimer = forecastPollTimer;

  modules.registerShutdownCallback(function () {
    if (forecastPollTimer) {
      clearInterval(forecastPollTimer);
      if (window.__apaForecastPollTimer === forecastPollTimer) {
        window.__apaForecastPollTimer = null;
      }
      forecastPollTimer = null;
    }
  });

  window["apa"] = self;
}
//
// //-----------------------------------------------------------------------------
// // Uses:
// //   Called when page loads.
// //-----------------------------------------------------------------------------
// $( document ).ready
// (
//   function()
//   {
//     //winder.inhibitUpdates()
//     apa = new APA()
//   }
// )
//
//
