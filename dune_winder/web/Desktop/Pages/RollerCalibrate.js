function RollerCalibrate(modules) {
  try {
    var uiServices = modules.get("UiServices");
  } catch (e) {
    console.error("Failed to initialize RollerCalibrate: " + e.message);
    return;
  }

  var calibrationState = null;
  var lastComputedResult = null;

  function pageAction(commandName, args, callback) {
    uiServices.call(
      commandName,
      args,
      function(data) {
        if (callback) callback(data);
      },
      function(response) {
        var errorMessage = "Command failed.";
        if (response && response.error && response.error.message)
          errorMessage = response.error.message;
        $("#rollerCalibrateError")
          .text("Error: " + errorMessage)
          .removeClass("hidden");
      }
    );
  }

  function formatNumber(value, decimals) {
    if (!$.isNumeric(value)) return "-";
    var multiplier = Math.pow(10, decimals);
    value = Math.round(value * multiplier) / multiplier;
    return value.toFixed(decimals);
  }

  function formatQuadrant(index, sign) {
    var xSign = ["-", "-", "+", "+"][index];
    var ySign = ["-", "+", "-", "+"][index];
    return xSign + "x," + ySign + "y";
  }

  function updateUI() {
    if (!calibrationState) return;

    var measurements = calibrationState.measurements || [];
    var fittedYCals = calibrationState.fitted_y_cals || [7.0, 7.0, 7.0, 7.0];
    var centerDisp = calibrationState.center_displacement || 0.0;
    var armTilt = calibrationState.arm_tilt_rad || 0.0;

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
      measurements.forEach(function (m, idx) {
        var delta = m.y_cal - nominalY;
        var row =
          "<tr>" +
          "<td>" +
          (idx + 1) +
          "</td>" +
          "<td>" +
          m.gcode_line +
          "</td>" +
          "<td>" +
          formatQuadrant(m.roller_index) +
          "</td>" +
          '<td class="numeric">' +
          formatNumber(m.y_cal, 2) +
          "</td>" +
          '<td class="numeric">' +
          formatNumber(delta, 2) +
          "</td>" +
          '<td><button class="rollerCalibrateDeleteBtn" data-idx="' +
          idx +
          '">Delete</button></td>' +
          "</tr>";
        tbody.append(row);
      });

      $(".rollerCalibrateDeleteBtn").on("click", function () {
        var idx = parseInt($(this).data("idx"));
        deleteMeasurement(idx);
      });
    }

    for (var i = 0; i < 4; i++) {
      var delta = fittedYCals[i] - nominalY;
      $("#nominalY" + i).text(formatNumber(nominalY, 2));
      $("#calibratedY" + i).text(formatNumber(fittedYCals[i], 2));
      $("#deltaY" + i).text(formatNumber(delta, 2));
    }

    $("#rollerCalibrateCenterDisp").text(formatNumber(centerDisp, 2) + " mm");

    var tiltDeg = (armTilt * 180) / Math.PI;
    $("#rollerCalibrateArmTilt").text(
      formatNumber(armTilt, 3) + " rad (" + formatNumber(tiltDeg, 2) + "°)"
    );
  }

  function loadCalibration() {
    pageAction(
      "machine.get_roller_arm_calibration",
      {},
      function (result) {
        calibrationState = result;
        updateUI();
      }
    );
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
      function (result) {
        lastComputedResult = result;
        var quadrant = result.quadrant || "unknown";
        var yCalText =
          "Roller " +
          quadrant +
          " (index " +
          result.roller_index +
          ")  y_cal = " +
          formatNumber(result.y_cal, 2) +
          "  Δ = " +
          formatNumber(result.y_cal_delta, 2);

        $("#rollerCalibrateResultText").text(yCalText);
        $("#rollerCalibrateResult").removeClass("hidden");
      }
    );
  }

  function addMeasurement() {
    if (!lastComputedResult) {
      $("#rollerCalibrateError")
        .text("Please compute a result first.")
        .removeClass("hidden");
      return;
    }

    var gcodeLine = $("#rollerCalibrateGCodeLine").val().trim();
    var actualX = parseFloat($("#rollerCalibrateActualX").val());
    var actualY = parseFloat($("#rollerCalibrateActualY").val());
    var layer = $("#rollerCalibrateLayer").val();

    pageAction(
      "machine.add_roller_arm_measurement",
      {
        gcode_line: gcodeLine,
        actual_x: actualX,
        actual_y: actualY,
        layer: layer,
      },
      function (result) {
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

    var measurements = calibrationState.measurements || [];
    measurements.splice(idx, 1);

    if (measurements.length === 0) {
      clearCalibration();
    } else {
      var head_arm_length = 77.0;
      var nominal_y = 7.0;

      var A = [];
      var b = [];
      measurements.forEach(function (m) {
        var rollerIdx = m.roller_index;
        var ySign = ["-", "+", "-", "+"][rollerIdx] === "-" ? -1 : 1;
        var dy = m.y_cal - nominal_y;

        A.push([-1.0, head_arm_length * ySign]);
        b.push(dy);
      });

      var result = leastSquaresFit(A, b);
      var deltaY = result.deltaY;
      var theta = result.theta;

      var fittedYCals = predictAllRollers(nominal_y, deltaY, theta, head_arm_length);

      var updatedCal = {
        measurements: measurements,
        fitted_y_cals: fittedYCals,
        center_displacement: deltaY,
        arm_tilt_rad: theta,
      };

      pageAction(
        "machine.save_calibration",
        {},
        function () {
          calibrationState = updatedCal;
          updateUI();
        }
      );
    }
  }

  function clearCalibration() {
    if (!confirm("Clear all measurements?")) return;

    pageAction(
      "machine.clear_roller_arm_calibration",
      {},
      function (result) {
        calibrationState = result;
        updateUI();
      }
    );
  }

  function saveCalibration() {
    pageAction(
      "machine.save_calibration",
      {},
      function () {
        $("#rollerCalibrateResult")
          .addClass("hidden")
          .removeClass("hidden")
          .html("<h3>✓ Calibration saved.</h3>");
      }
    );
  }

  function leastSquaresFit(A, b) {
    if (!A || A.length === 0) {
      return { deltaY: 0, theta: 0 };
    }

    var AtA_00 = 0,
      AtA_01 = 0,
      AtA_11 = 0;
    var ATb_0 = 0,
      ATb_1 = 0;

    for (var i = 0; i < A.length; i++) {
      AtA_00 += A[i][0] * A[i][0];
      AtA_01 += A[i][0] * A[i][1];
      AtA_11 += A[i][1] * A[i][1];
      ATb_0 += A[i][0] * b[i];
      ATb_1 += A[i][1] * b[i];
    }

    var det = AtA_00 * AtA_11 - AtA_01 * AtA_01;
    if (Math.abs(det) < 1e-9) {
      return { deltaY: 0, theta: 0 };
    }

    var inv_00 = AtA_11 / det;
    var inv_01 = -AtA_01 / det;
    var inv_10 = -AtA_01 / det;
    var inv_11 = AtA_00 / det;

    var deltaY = inv_00 * ATb_0 + inv_01 * ATb_1;
    var theta = inv_10 * ATb_0 + inv_11 * ATb_1;

    return { deltaY: deltaY, theta: theta };
  }

  function predictAllRollers(nominalY, deltaY, theta, headArmLength) {
    var yCals = [];
    for (var i = 0; i < 4; i++) {
      var ySign = ["-", "+", "-", "+"][i] === "-" ? -1 : 1;
      var dy = -deltaY + headArmLength * theta * ySign;
      yCals.push(nominalY + dy);
    }
    return yCals;
  }

  try {
    $("#rollerCalibrateComputeButton").on("click", computeYCal);
    $("#rollerCalibrateAddButton").on("click", addMeasurement);
    $("#rollerCalibrateClearButton").on("click", clearCalibration);
    $("#rollerCalibrateSaveButton").on("click", saveCalibration);

    loadCalibration();
  } catch (e) {
    console.error("Failed to bind RollerCalibrate controls: " + e.message);
  }
}
