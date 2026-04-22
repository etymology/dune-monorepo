function ZPlaneCalibrate(modules) {
  try {
    var uiServices = modules.get("UiServices");
    var page = modules.get("Page");
    var commands = uiServices.getCommands();
  } catch (e) {
    console.error("Failed to initialize ZPlaneCalibrate: " + e.message);
    return;
  }

  var calibrationState = null;
  var motorStatus = null;
  var isBusy = false;

  function commandName(path, fallback) {
    return path || fallback;
  }

  function setBusy(nextBusy) {
    isBusy = !!nextBusy;
    $("#zPlaneCalibrateAddButton").prop("disabled", isBusy);
    $("#zPlaneCalibrateRefreshButton").prop("disabled", isBusy);
    $("#zPlaneCalibrateClearButton").prop("disabled", isBusy);
    $("#zPlaneCalibrateUseGCodeButton").prop("disabled", isBusy);
    $("#zPlaneCalibrateUseZButton").prop("disabled", isBusy);
    $("#zPlaneCalibrateLayer").prop("disabled", isBusy);
  }

  function clearError() {
    $("#zPlaneCalibrateError").addClass("hidden").text("");
  }

  function showError(message) {
    $("#zPlaneCalibrateError").text("Error: " + message).removeClass("hidden");
  }

  function clearMessage() {
    $("#zPlaneCalibrateMessage").addClass("hidden").text("");
  }

  function showMessage(message) {
    $("#zPlaneCalibrateMessage").text(message).removeClass("hidden");
  }

  function pageAction(command, args, callback, options) {
    options = options || {};
    uiServices.call(
      command,
      args,
      function(data) {
        if (!options.keepMessage) clearMessage();
        clearError();
        if (callback) callback(data);
      },
      function(response) {
        var errorMessage = "Command failed.";
        if (response && response.error && response.error.message) {
          errorMessage = response.error.message;
        }
        showError(errorMessage);
        if (options.onError) options.onError(response);
      }
    );
  }

  function formatNumber(value, decimals) {
    if (!$.isNumeric(value)) return "-";
    var multiplier = Math.pow(10, decimals);
    value = Math.round(value * multiplier) / multiplier;
    return value.toFixed(decimals);
  }

  function formatSignedTerm(value, symbol) {
    if (!$.isNumeric(value)) return "-";
    var prefix = value >= 0 ? "+" : "-";
    return prefix + " " + formatNumber(Math.abs(value), 6) + symbol;
  }

  function currentLayer() {
    return ($("#zPlaneCalibrateLayer").val() || "").trim().toUpperCase();
  }

  function tracePosition() {
    var x = 0.0;
    var y = 0.0;
    if (motorStatus && motorStatus.motor) {
      if ($.isNumeric(motorStatus.motor["xPosition"])) {
        x = parseFloat(motorStatus.motor["xPosition"]);
      }
      if ($.isNumeric(motorStatus.motor["yPosition"])) {
        y = parseFloat(motorStatus.motor["yPosition"]);
      }
    }
    return { x: x, y: y };
  }

  function applyRecipeLayer(layer) {
    var normalized = (layer || "").toString().trim().toUpperCase();
    if (normalized === "U" || normalized === "V") {
      $("#zPlaneCalibrateLayer").val(normalized);
      $("#zPlaneCalibrateLayerHint").text(
        "Active recipe layer is " + normalized + ". Measurements must target the active recipe layer."
      );
      return true;
    }

    $("#zPlaneCalibrateLayerHint").text(
      "Load an active U or V recipe before using Z plane calibration."
    );
    return false;
  }

  function loadActiveLayer(callback) {
    pageAction(
      commandName(commands.process.getRecipeLayer, "process.get_recipe_layer"),
      {},
      function(layer) {
        var isSupported = applyRecipeLayer(layer);
        if (callback) callback(isSupported);
      }
    );
  }

  function loadLastExecutedLine() {
    function extractAnchorToTargetCommand(lineText) {
      var text = String(lineText || "");
      var start = text.indexOf("~anchorToTarget(");
      if (start < 0) return null;

      var depth = 0;
      for (var i = start; i < text.length; i++) {
        var ch = text.charAt(i);
        if (ch === "(") {
          depth++;
        } else if (ch === ")") {
          depth--;
          if (depth === 0) {
            return text.slice(start, i + 1);
          }
        }
      }
      return null;
    }

    pageAction(
      commandName(commands.process.getGCodeLine, "process.get_gcode_line"),
      {},
      function(currentLine) {
        if (currentLine === null || currentLine === undefined || currentLine < 0) {
          showError("No active G-code line is available.");
          return;
        }

        pageAction(
          commandName(commands.process.getGCodeList, "process.get_gcode_list"),
          { center: currentLine, delta: 0 },
          function(lines) {
            var lineText = currentLine;
            if (lines && lines.length > 0 && lines[0]) {
              lineText = lines[0];
            }
            var commandText = extractAnchorToTargetCommand(lineText);
            if (!commandText) {
              showError("Last G-code line does not contain an ~anchorToTarget command.");
              return;
            }
            $("#zPlaneCalibrateGCodeLine").val(commandText);
          }
        );
      }
    );
  }

  function useCurrentZ() {
    if (!motorStatus || !motorStatus.motor || !$.isNumeric(motorStatus.motor["zPosition"])) {
      showError("Current Z position is not available.");
      return;
    }
    $("#zPlaneCalibrateActualZ").val(motorStatus.motor["zPosition"]);
    clearError();
  }

  function fitStatusText(state) {
    var measurementCount = (state.measurements || []).length;
    if (measurementCount === 0) {
      return "No measurements recorded yet.";
    }
    if (state.fit_error) {
      return state.fit_error;
    }
    if (state.coefficients && state.coefficients.length === 3) {
      return "Fit valid.";
    }
    return "Waiting for enough non-collinear tangent points.";
  }

  function renderEquations(state) {
    var coefficients = state.coefficients || null;
    if (!coefficients || coefficients.length !== 3) {
      $("#zPlaneCalibrateEquationA").text("-");
      $("#zPlaneCalibrateEquationB").text("-");
      return;
    }

    var a = coefficients[0];
    var b = coefficients[1];
    var c = coefficients[2];
    var boardWidth = $.isNumeric(state.board_width) ? parseFloat(state.board_width) : 130.0;

    $("#zPlaneCalibrateEquationA").text(
      "z_A(x,y) = " +
        formatNumber(a, 6) +
        "x " +
        formatSignedTerm(b, "y") +
        " " +
        (c >= 0 ? "+ " : "- ") +
        formatNumber(Math.abs(c), 6)
    );
    $("#zPlaneCalibrateEquationB").text(
      "z_B(x,y) = z_A(x,y) + " + formatNumber(boardWidth, 3)
    );
  }

  function renderMeasurements(state) {
    var measurements = state.measurements || [];
    var observations = state.observations || [];

    $("#zPlaneCalibrateCount").text(
      measurements.length === 0
        ? "No measurements recorded."
        : measurements.length +
            " measurement" +
            (measurements.length === 1 ? "" : "s") +
            " recorded. Calibration is saved after each add."
    );

    if (measurements.length === 0) {
      $("#zPlaneCalibrateMeasurementsTable").addClass("hidden");
      $("#zPlaneCalibrateMeasurementsBody").empty();
      return;
    }

    var tbody = $("#zPlaneCalibrateMeasurementsBody");
    tbody.empty();
    $("#zPlaneCalibrateMeasurementsTable").removeClass("hidden");

    measurements.forEach(function(measurement, index) {
      var observation = observations[index] || {};
      var residualText = observation.residual === null || observation.residual === undefined
        ? "-"
        : formatNumber(observation.residual, 4);
      var tangentX = observation.effective_x;
      var tangentY = observation.effective_y;
      var side = observation.pin_family || measurement.gcode_line.slice(17, 18) || "-";

      tbody.append(
        "<tr>" +
          "<td>" + (index + 1) + "</td>" +
          "<td>" + measurement.gcode_line + "</td>" +
          "<td>" + side + "</td>" +
          '<td class="numeric">' + formatNumber(tangentX, 3) + "</td>" +
          '<td class="numeric">' + formatNumber(tangentY, 3) + "</td>" +
          '<td class="numeric">' + formatNumber(measurement.actual_z, 3) + "</td>" +
          '<td class="numeric">' + residualText + "</td>" +
          '<td><button class="zPlaneCalibrateDeleteBtn" data-idx="' + index + '">Delete</button></td>' +
        "</tr>"
      );
    });

    $(".zPlaneCalibrateDeleteBtn").on("click", function() {
      deleteMeasurement(parseInt($(this).data("idx"), 10));
    });
  }

  function renderFit(state) {
    $("#zPlaneCalibrateFitStatus").text(fitStatusText(state));
    $("#zPlaneCalibrateRank").text(
      state.rank === null || state.rank === undefined ? "-" : state.rank
    );
    $("#zPlaneCalibrateResidual").text(formatNumber(state.residual_sum_squares, 6));
    $("#zPlaneCalibrateMaxDeviation").text(
      $.isNumeric(state.max_abs_side_deviation_mm)
        ? formatNumber(state.max_abs_side_deviation_mm, 3) + " mm"
        : "-"
    );
    $("#zPlaneCalibrateMeanA").text(formatNumber(state.z_front_mean, 3));
    $("#zPlaneCalibrateMeanB").text(formatNumber(state.z_back_mean, 3));
    $("#zPlaneCalibrateBoardWidth").text(formatNumber(state.board_width, 3));
    renderEquations(state);
  }

  function updateUI() {
    var state = calibrationState || {
      measurements: [],
      observations: [],
      board_width: 130.0,
    };
    renderMeasurements(state);
    renderFit(state);
  }

  function loadCalibration(options) {
    options = options || {};
    pageAction(
      commandName(
        commands.process.getLayerZPlaneCalibration,
        "process.get_layer_z_plane_calibration"
      ),
      { layer: currentLayer() },
      function(result) {
        calibrationState = result;
        updateUI();
        if (options.message) showMessage(options.message);
      },
      {
        keepMessage: !!options.keepMessage,
        onError: function() {
          calibrationState = {
            measurements: [],
            observations: [],
            board_width: 130.0,
          };
          updateUI();
        },
      }
    );
  }

  function addMeasurement() {
    var gcodeLine = $("#zPlaneCalibrateGCodeLine").val().trim();
    var actualZ = parseFloat($("#zPlaneCalibrateActualZ").val());
    var layer = currentLayer();
    var trace = tracePosition();

    clearMessage();
    clearError();

    if (!gcodeLine || !$.isNumeric(actualZ)) {
      showError("Provide a same-side ~anchorToTarget(...) line and an observed Z value.");
      return;
    }

    pageAction(
      commandName(
        commands.process.addLayerZPlaneMeasurement,
        "process.add_layer_z_plane_measurement"
      ),
      {
        gcode_line: gcodeLine,
        actual_x: trace.x,
        actual_y: trace.y,
        actual_z: actualZ,
        layer: layer,
      },
      function(result) {
        calibrationState = result;
        updateUI();
        showMessage(
          "Measurement added. Fit status: " + fitStatusText(result)
        );
      }
    );
  }

  function clearCalibration() {
    if (!confirm("Clear all stored Z-plane measurements for layer " + currentLayer() + "?")) {
      return;
    }

    pageAction(
      commandName(
        commands.process.clearLayerZPlaneCalibration,
        "process.clear_layer_z_plane_calibration"
      ),
      { layer: currentLayer() },
      function(result) {
        calibrationState = result;
        updateUI();
        showMessage(
          "Stored measurements cleared. Existing fitted pin Z values remain until a new valid fit replaces them."
        );
      }
    );
  }

  function replayMeasurements(measurements, onDone) {
    setBusy(true);
    pageAction(
      commandName(
        commands.process.clearLayerZPlaneCalibration,
        "process.clear_layer_z_plane_calibration"
      ),
      { layer: currentLayer() },
      function(result) {
        calibrationState = result;
        updateUI();

        function addNext(index) {
          if (index >= measurements.length) {
            setBusy(false);
            loadCalibration({
              message: "Measurement set rebuilt.",
              keepMessage: false,
            });
            if (onDone) onDone();
            return;
          }

          var measurement = measurements[index];
          pageAction(
            commandName(
              commands.process.addLayerZPlaneMeasurement,
              "process.add_layer_z_plane_measurement"
            ),
            {
              gcode_line: measurement.gcode_line,
              actual_x: measurement.actual_x,
              actual_y: measurement.actual_y,
              actual_z: measurement.actual_z,
              layer: measurement.layer,
            },
            function(nextState) {
              calibrationState = nextState;
              updateUI();
              addNext(index + 1);
            },
            {
              onError: function() {
                setBusy(false);
              },
            }
          );
        }

        addNext(0);
      },
      {
        onError: function() {
          setBusy(false);
        },
      }
    );
  }

  function deleteMeasurement(index) {
    if (!calibrationState || !calibrationState.measurements) return;
    if (!confirm("Delete measurement " + (index + 1) + " and rebuild the fit?")) {
      return;
    }

    var remaining = calibrationState.measurements.slice();
    remaining.splice(index, 1);
    replayMeasurements(remaining);
  }

  function bindEvents() {
    $("#zPlaneCalibrateAddButton").on("click", addMeasurement);
    $("#zPlaneCalibrateRefreshButton").on("click", function() {
      loadCalibration();
    });
    $("#zPlaneCalibrateClearButton").on("click", clearCalibration);
    $("#zPlaneCalibrateUseGCodeButton").on("click", loadLastExecutedLine);
    $("#zPlaneCalibrateUseZButton").on("click", useCurrentZ);
    $("#zPlaneCalibrateLayer").on("change", function() {
      clearMessage();
      clearError();
      loadCalibration();
    });
  }

  try {
    page.loadSubPage("/Desktop/Modules/MotorStatus", "#zPlaneCalibrateMotorStatus", function() {
      motorStatus = modules.get("MotorStatus");
    });

    bindEvents();
    loadActiveLayer(function(isSupported) {
      if (isSupported) {
        loadCalibration();
      } else {
        calibrationState = {
          measurements: [],
          observations: [],
          board_width: 130.0,
        };
        updateUI();
      }
    });
  } catch (e) {
    console.error("Failed to bind ZPlaneCalibrate controls: " + e.message);
  }
}
