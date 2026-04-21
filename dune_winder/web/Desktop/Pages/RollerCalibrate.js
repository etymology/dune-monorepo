function RollerCalibrate(modules) {
  try {
    var uiServices = modules.get("UiServices");
    var page = modules.get("Page");
  } catch (e) {
    console.error("Failed to initialize RollerCalibrate: " + e.message);
    return;
  }

  var calibrationState = null;
  var lastComputedResult = null;
  var motorStatus = null;

  function pageAction(commandName, args, callback) {
    uiServices.call(
      commandName,
      args,
      function(data) {
        if (callback) callback(data);
      },
      function(response) {
        var errorMessage = "Command failed.";
        if (response && response.error && response.error.message) {
          errorMessage = response.error.message;
        }
        $("#rollerCalibrateError").text("Error: " + errorMessage).removeClass("hidden");
      }
    );
  }

  function formatNumber(value, decimals) {
    if (!$.isNumeric(value)) return "-";
    var multiplier = Math.pow(10, decimals);
    value = Math.round(value * multiplier) / multiplier;
    return value.toFixed(decimals);
  }

  function formatQuadrant(index) {
    var xSign = ["-", "-", "+", "+"][index];
    var ySign = ["-", "+", "-", "+"][index];
    return xSign + "x," + ySign + "y";
  }

  function refreshMotorStatus() {
    if (!motorStatus || !motorStatus.motor) return;
    var x = motorStatus.motor["xPosition"];
    var y = motorStatus.motor["yPosition"];
    if ($.isNumeric(x)) $("#rollerCalibrateActualX").val(x);
    if ($.isNumeric(y)) $("#rollerCalibrateActualY").val(y);
  }

  function loadLastExecutedLine() {
    pageAction("process.get_gcode_line", {}, function(currentLine) {
      if (currentLine === null || currentLine === undefined || currentLine < 0) {
        $("#rollerCalibrateError")
          .text("No active G-code line is available.")
          .removeClass("hidden");
        return;
      }

      pageAction("process.get_gcode_list", { center: currentLine, delta: 0 }, function(lines) {
        var lineText = currentLine;
        if (lines && lines.length > 0 && lines[0]) {
          lineText = lines[0];
        }
        $("#rollerCalibrateGCodeLine").val(lineText);
      });
    });
  }

  function updateUI() {
    if (!calibrationState) return;

    var measurements = calibrationState.measurements || [];
    var fittedYCals = calibrationState.fitted_y_cals || [7.0, 7.0, 7.0, 7.0];

    $("#rollerCalibrateCount").text(
      measurements.length === 0
        ? "No measurements recorded."
        : measurements.length +
            " measurement" +
            (measurements.length === 1 ? "" : "s") +
            " recorded."
    );

    var nominalY = 7.0;
    if (measurements.length === 0) {
      $("#rollerCalibrateMeasurementsTable").addClass("hidden");
    } else {
      $("#rollerCalibrateMeasurementsTable").removeClass("hidden");
      var tbody = $("#rollerCalibrateMeasurementsBody");
      tbody.empty();
      measurements.forEach(function(m, idx) {
        var delta = m.y_cal - nominalY;
        tbody.append(
          "<tr>" +
            "<td>" + (idx + 1) + "</td>" +
            "<td>" + m.gcode_line + "</td>" +
            "<td>" + formatQuadrant(m.roller_index) + "</td>" +
            '<td class="numeric">' + formatNumber(m.y_cal, 2) + "</td>" +
            '<td class="numeric">' + formatNumber(delta, 2) + "</td>" +
            '<td><button class="rollerCalibrateDeleteBtn" data-idx="' + idx + '">Delete</button></td>' +
          "</tr>"
        );
      });

      $(".rollerCalibrateDeleteBtn").on("click", function() {
        deleteMeasurement(parseInt($(this).data("idx")));
      });
    }

    for (var i = 0; i < 4; i++) {
      var rollerDelta = fittedYCals[i] - nominalY;
      $("#nominalY" + i).text(formatNumber(nominalY, 2));
      $("#calibratedY" + i).text(formatNumber(fittedYCals[i], 2));
      $("#deltaY" + i).text(formatNumber(rollerDelta, 2));
    }

    $("#rollerCalibrateCenterDisp").text(
      "Independent per-roller offsets are stored exactly; fitted center displacement is " +
        formatNumber(calibrationState.center_displacement || 0.0, 2) +
        " mm"
    );
    $("#rollerCalibrateArmTilt").text(
      "Independent per-roller offsets are stored exactly; fitted arm tilt is " +
        formatNumber(calibrationState.arm_tilt_rad || 0.0, 3) +
        " rad"
    );
  }

  function loadCalibration() {
    pageAction("machine.get_roller_arm_calibration", {}, function(result) {
      calibrationState = result;
      updateUI();
    });
  }

  function computeYCal() {
    var gcodeLine = $("#rollerCalibrateGCodeLine").val().trim();
    var actualX = parseFloat($("#rollerCalibrateActualX").val());
    var actualY = parseFloat($("#rollerCalibrateActualY").val());
    var layer = $("#rollerCalibrateLayer").val();

    $("#rollerCalibrateError").addClass("hidden");
    $("#rollerCalibrateResult").addClass("hidden");

    if (!gcodeLine || !$.isNumeric(actualX) || !$.isNumeric(actualY)) {
      $("#rollerCalibrateError").text("Please fill in all fields.").removeClass("hidden");
      return;
    }

    pageAction(
      "machine.compute_roller_y_cal",
      {
        gcode_line: gcodeLine,
        actual_x: actualX,
        actual_y: actualY,
        layer: layer,
      },
      function(result) {
        lastComputedResult = result;
        $("#rollerCalibrateResultText").text(
          "Roller " +
            (result.quadrant || "unknown") +
            " (index " +
            result.roller_index +
            ")  y_cal = " +
            formatNumber(result.y_cal, 2) +
            "  delta = " +
            formatNumber(result.y_cal_delta, 2)
        );
        $("#rollerCalibrateResult").removeClass("hidden");
      }
    );
  }

  function addMeasurement() {
    if (!lastComputedResult) {
      $("#rollerCalibrateError").text("Please compute a result first.").removeClass("hidden");
      return;
    }

    pageAction(
      "machine.add_roller_arm_measurement",
      {
        gcode_line: $("#rollerCalibrateGCodeLine").val().trim(),
        actual_x: parseFloat($("#rollerCalibrateActualX").val()),
        actual_y: parseFloat($("#rollerCalibrateActualY").val()),
        layer: $("#rollerCalibrateLayer").val(),
      },
      function(result) {
        calibrationState = result;
        updateUI();
        $("#rollerCalibrateGCodeLine").val("");
        $("#rollerCalibrateActualX").val("");
        $("#rollerCalibrateActualY").val("");
        $("#rollerCalibrateResult").addClass("hidden");
        lastComputedResult = null;
      }
    );
  }

  function deleteMeasurement(idx) {
    if (!confirm("Delete measurement " + (idx + 1) + "?")) return;

    var measurements = (calibrationState.measurements || []).slice();
    measurements.splice(idx, 1);

    if (measurements.length === 0) {
      clearCalibration();
      return;
    }

    var nominalY = 7.0;
    var fittedYCals = [nominalY, nominalY, nominalY, nominalY];
    measurements.forEach(function(m) {
      fittedYCals[m.roller_index] = m.y_cal;
    });

    pageAction(
      "machine.set_roller_arm_calibration",
      {
        calibration: {
          measurements: measurements,
          fitted_y_cals: fittedYCals,
          center_displacement: 0.0,
          arm_tilt_rad: 0.0,
        },
      },
      function(result) {
        calibrationState = result;
        updateUI();
      }
    );
  }

  function clearCalibration() {
    if (!confirm("Clear all measurements?")) return;
    pageAction("machine.clear_roller_arm_calibration", {}, function(result) {
      calibrationState = result;
      updateUI();
    });
  }

  function saveCalibration() {
    pageAction(
      "machine.set_roller_arm_calibration",
      { calibration: calibrationState },
      function(result) {
        calibrationState = result;
        $("#rollerCalibrateResult")
          .addClass("hidden")
          .removeClass("hidden")
          .html("<h3>Calibration saved.</h3>");
        updateUI();
      }
    );
  }

  try {
    page.loadSubPage("/Desktop/Modules/MotorStatus", "#rollerCalibrateMotorStatus", function() {
      motorStatus = modules.get("MotorStatus");
      refreshMotorStatus();
    });

    $("#rollerCalibrateComputeButton").on("click", computeYCal);
    $("#rollerCalibrateAddButton").on("click", addMeasurement);
    $("#rollerCalibrateClearButton").on("click", clearCalibration);
    $("#rollerCalibrateSaveButton").on("click", saveCalibration);
    $("#rollerCalibrateUseGCodeButton").on("click", loadLastExecutedLine);
    $("#rollerCalibrateUsePositionButton").on("click", refreshMotorStatus);

    loadCalibration();
  } catch (e) {
    console.error("Failed to bind RollerCalibrate controls: " + e.message);
  }
}
