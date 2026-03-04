function PositionGraphic(modules) {
  var self = this;

  // Number of path lines to leave on screen.
  var LINES = 25;

  // Default scale factor for all images.
  var DEFAULT_SCALE = 1.0;
  // Slightly shrink auto/applied scaling so the full graphic fits page margins.
  var GRAPHIC_FIT_SCALE = 0.9;

  // Limits of image (in pixels).
  // Simi-constants come from images used.  Simi-constant because they are
  // scaled at class creation.
  var BASE_GRAPHIC_X = 1286;
  var BASE_GRAPHIC_Y = 463;
  var SIDE_GRAPHIC_Y = BASE_GRAPHIC_Y + 80;
  var Z_GRAPHIC_X = 1500;
  var Z_GRAPHIC_Y = 332;
  var MIN_X = 95;
  var MAX_X = 1065;
  var MIN_Y = 393;
  var MAX_Y = 17;
  var HEAD_X_OFFSET = 100;
  var MIN_ARM_Z = 0;
  var MAX_ARM_Z = 281;
  var MIN_HEAD_Z = 783;
  var MAX_HEAD_Z = 1064;
  var LINE_OFFSET_X = 129;
  var LINE_OFFSET_Y = 30;
  var Z_HEAD_ARM_X = 843;
  var Z_HEAD_ARM_Y = 105;
  var Z_HEAD_ARM_MIN_WIDTH = 20;
  var Z_HEAD_ARM_MAX_WIDTH = 90;
  var Z_HEAD_ARM_HEIGHT = 20;
  var HEAD_ANGLE_X = 60;
  var HEAD_ANGLE_Y = 60;
  var HEAD_ANGLE_RADIUS = 50;

  var winder;
  var motorStatus;
  var runStatus;

  // Images to hide if server stops communicating.
  var IMAGES_TO_HIDE = [
    "#pathCanvas",
    "#seekCanvas",
    "#zStatusCanvas",
    "#xyStatusCanvas",
  ];

  // Images to blur if server stops communicating.
  var IMAGES_TO_BLUR = [
    "#loopImage",
    "#headImage",
    "#zHeadImage",
    "#zArmImage",
  ];

  // Scale factor for all images.
  var scale;

  // Position debouce to keep deal with the asynchronous nature of desired X/Y
  // positions.
  var debounceLastX = null;
  var debounceLastY = null;
  var debounceX = null;
  var debounceY = null;

  var motorX = null;
  var motorY = null;
  var wasMoving = false;

  var lastX = null;
  var lastY = null;
  var startingX = null;
  var startingY = null;
  var lines = [];

  var machineCaliration;
  var inputs;

  //---------------------------------------------------------------------------
  // Uses:
  //   Set the state of a status light on the Z image.
  // Input:
  //   x - Location in x.
  //   y - Location in y.
  //   status - State of light.
  //   offIsError - False if being off (false) is ok, or true if this is an error.
  //---------------------------------------------------------------------------
  var statusLight = function (statusCanvas, x, y, status, offIsError) {
    // Scale locations.
    x *= scale;
    y *= scale;

    // Select the color of the light indicator.
    if (status) {
      statusCanvas.fillStyle = "lime";
      statusCanvas.strokeStyle = "green";
    } else if (!offIsError) {
      statusCanvas.fillStyle = "blue";
      statusCanvas.strokeStyle = "darkBlue";
    } else {
      statusCanvas.fillStyle = "red";
      statusCanvas.strokeStyle = "darkRed";
    }

    // Draw a circle at the specified location.
    statusCanvas.beginPath();
    statusCanvas.arc(x, y, 8 * scale, 0, 2 * Math.PI);

    // Draw fill (do before border).
    statusCanvas.fill();

    // Draw border.
    statusCanvas.lineWidth = 2 * scale;
    statusCanvas.stroke();
  };

  //---------------------------------------------------------------------------
  // Uses:
  //   EXPERIMENTAL
  //Set the state of a status BAR light on the image.
  // Input:
  //   x - Location in x.
  //   y - Location in y.
  //   status - State of light.
  //   offIsError - False if being off (false) is ok, or true if this is an error.
  //---------------------------------------------------------------------------
  var statusLightBar = function (statusCanvas, x, y, status, offIsError) {
    // Scale locations.
    x *= scale;
    y *= scale;

    // Select the color of the light indicator.
    if (status) {
      statusCanvas.fillStyle = "lime";
      statusCanvas.strokeStyle = "green";
    } else if (!offIsError) {
      statusCanvas.fillStyle = "blue";
      statusCanvas.strokeStyle = "darkBlue";
    } else {
      statusCanvas.fillStyle = "red";
      statusCanvas.strokeStyle = "red";
    }

    // Draw a BAR at the specified location.
    statusCanvas.beginPath();
    statusCanvas.moveTo(x, y);
    statusCanvas.lineTo(x + 50, y);

    // Draw fill (do before border).
    statusCanvas.fill();

    // Draw border.
    statusCanvas.lineWidth = 10 * scale;
    statusCanvas.stroke();
  };

  //---------------------------------------------------------------------------
  // Uses:
  //   Get a canvas context by name.
  //---------------------------------------------------------------------------
  function getCanvas(canvasName) {
    var canvas = document.getElementById(canvasName);
    var context;

    if (canvas) context = canvas.getContext("2d");

    return context;
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Callback run after machine calibration has been acquired.  Sets up
  //   periodic function to update graphics.
  //---------------------------------------------------------------------------
  var setupCallback = function () {
    var baseGraphicWidth = BASE_GRAPHIC_X * scale;
    var baseGraphicHeight = BASE_GRAPHIC_Y * scale;
    var sideGraphicHeight = SIDE_GRAPHIC_Y * scale;

    // Scale limits of image.
    Z_GRAPHIC_X *= scale;
    Z_GRAPHIC_Y *= scale;
    MIN_X *= scale;
    MAX_X *= scale;
    MIN_Y *= scale;
    MAX_Y *= scale;
    HEAD_X_OFFSET *= scale;
    MIN_ARM_Z *= scale;
    MAX_ARM_Z *= scale;
    MIN_HEAD_Z *= scale;
    MAX_HEAD_Z *= scale;
    LINE_OFFSET_X *= scale;
    LINE_OFFSET_Y *= scale;
    Z_HEAD_ARM_X *= scale;
    Z_HEAD_ARM_Y *= scale;
    Z_HEAD_ARM_MIN_WIDTH *= scale;
    Z_HEAD_ARM_MAX_WIDTH *= scale;
    Z_HEAD_ARM_HEIGHT *= scale;
    HEAD_ANGLE_X *= scale;
    HEAD_ANGLE_Y *= scale;
    HEAD_ANGLE_RADIUS *= scale;

    // Limits of travel (in mm).
    var MIN_X_POSITION = machineCaliration["limitLeft"];
    var MAX_X_POSITION = machineCaliration["limitRight"];
    var MIN_Y_POSITION = machineCaliration["limitBottom"];
    var MAX_Y_POSITION = machineCaliration["limitTop"];
    var MIN_Z_POSITION = machineCaliration["zFront"];
    var MAX_Z_POSITION = machineCaliration["zBack"];

    $("#pathCanvas")
      .attr("width", baseGraphicWidth + "px")
      .attr("height", baseGraphicHeight + "px");

    $("#seekCanvas")
      .attr("width", baseGraphicWidth + "px")
      .attr("height", baseGraphicHeight + "px");

    $("#xyStatusCanvas")
      .attr("width", baseGraphicWidth + "px")
      .attr("height", sideGraphicHeight + "px");

    $("#zStatusCanvas")
      .attr("width", Z_GRAPHIC_X + "px")
      .attr("height", Z_GRAPHIC_Y + "px");

    // Image position
    winder.addPeriodicEndCallback(
      function () {
        if (!motorStatus.motor["yFunctional"])
          $("#loopImage").addClass("axisFault");
        else $("#loopImage").removeClass("axisFault");

        // Motor position history.
        debounceLastX = debounceX;
        debounceLastY = debounceY;
        debounceX = Math.round(motorStatus.motor["xDesiredPosition"]);
        debounceY = Math.round(motorStatus.motor["yDesiredPosition"]);

        // Debounce motor positions.
        // This is done because the X and Y destinations change asynchronously.
        // To ensure they stay in step, they both must match their previous
        // value twice in a row.
        if (debounceLastX == debounceX && debounceLastY == debounceY) {
          motorX = debounceX;
          motorY = debounceY;
        }

        // Rescale value based on sizes.
        var rescale = function (value, outMin, outMax, inMin, inMax, offset) {
          var result = outMax - outMin;
          result *= value - inMin;
          result /= inMax - inMin;
          result += outMin + offset;

          return result;
        };

        // Axis positions.  Round to keep graphic from jittering.
        var xPosition = Math.round(motorStatus.motor["xPosition"]);
        var yPosition = Math.round(motorStatus.motor["yPosition"]);
        var zPosition = Math.round(motorStatus.motor["zPosition"]);
        var headAngle = motorStatus.motor["headAngle"];
        if (!$.isNumeric(headAngle)) headAngle = 0;

        //
        // Position loop (X/Y image).
        //

        var loopX = rescale(
          xPosition,
          MIN_X,
          MAX_X,
          MIN_X_POSITION,
          MAX_X_POSITION,
          0,
        );

        $("#loopImage").css("left", loopX + "px");

        //
        // Position head (X/Y image).
        //
        var y = rescale(
          yPosition,
          MIN_Y,
          MAX_Y,
          MIN_Y_POSITION,
          MAX_Y_POSITION,
          0,
        );
        var x = loopX + HEAD_X_OFFSET;

        $("#headImage")
          .css("left", x + "px")
          .css("top", y + "px");

        //
        // Position head (Z image).
        //
        var zStatusCanvas = getCanvas("zStatusCanvas");
        zStatusCanvas.clearRect(0, 0, Z_GRAPHIC_X, Z_GRAPHIC_Y);

        var zArm = rescale(
          zPosition,
          MIN_ARM_Z,
          MAX_ARM_Z,
          MIN_Z_POSITION,
          MAX_Z_POSITION,
          0,
        );

        if (0 != motorStatus.motor["headSide"]) {
          var zHead = rescale(
            zPosition,
            MIN_HEAD_Z,
            MAX_HEAD_Z,
            MIN_Z_POSITION,
            MAX_Z_POSITION,
            0,
          );

          if (1 != motorStatus.motor["headSide"]) zHead = MAX_HEAD_Z;

          $("#zHeadImage")
            .show()
            .css("left", zHead + "px");

          //
          // Position arm (Z image).
          //
          $("#zArmImage").css("left", zArm + "px");

          //
          // Draw angle of arm on head.
          //
          var z = zPosition;
          if (1 != motorStatus.motor["headSide"]) z = MAX_Z_POSITION;

          var zHeadArm = rescale(
            z,
            MIN_ARM_Z,
            MAX_ARM_Z,
            MIN_Z_POSITION,
            MAX_Z_POSITION,
            Z_HEAD_ARM_X,
          );

          var zHeadArmWidth = Z_HEAD_ARM_MAX_WIDTH - Z_HEAD_ARM_MIN_WIDTH;
          zHeadArmWidth *= -Math.sin(headAngle);

          if (zHeadArmWidth < 0) {
            zHeadArm += zHeadArmWidth;
            zHeadArmWidth = Z_HEAD_ARM_MIN_WIDTH - zHeadArmWidth;
          } else zHeadArmWidth += Z_HEAD_ARM_MIN_WIDTH;

          zStatusCanvas.fillStyle = "grey";
          zStatusCanvas.fillRect(
            zHeadArm,
            Z_HEAD_ARM_Y,
            zHeadArmWidth,
            Z_HEAD_ARM_HEIGHT,
          );
          zStatusCanvas.strokeStyle = "black";
          zStatusCanvas.lineWidth = 1 * scale;
          zStatusCanvas.strokeRect(
            zHeadArm,
            Z_HEAD_ARM_Y,
            zHeadArmWidth,
            Z_HEAD_ARM_HEIGHT,
          );

          var radius = HEAD_ANGLE_RADIUS;
          zStatusCanvas.beginPath();
          zStatusCanvas.arc(HEAD_ANGLE_X, HEAD_ANGLE_Y, radius, 0, 2 * Math.PI);
          zStatusCanvas.lineWidth = 2 * scale;
          zStatusCanvas.stroke();

          zStatusCanvas.beginPath();
          var x = -Math.sin(headAngle) * radius;
          var y = Math.cos(headAngle) * radius;
          zStatusCanvas.moveTo(HEAD_ANGLE_X, HEAD_ANGLE_Y);
          zStatusCanvas.lineTo(x + HEAD_ANGLE_X, y + HEAD_ANGLE_Y);
          zStatusCanvas.lineWidth = 2 * scale;
          zStatusCanvas.stroke();
        } else $("#zHeadImage").hide();

        var xyStatusCanvas = getCanvas("xyStatusCanvas");
        xyStatusCanvas.clearRect(0, 0, baseGraphicWidth, sideGraphicHeight);

        // Head Locking Pins
        statusLightBar(
          xyStatusCanvas,
          250,
          100,
          !inputs["FrameLockHeadTop"],
          true,
        );
        statusLightBar(
          xyStatusCanvas,
          250,
          250,
          !inputs["FrameLockHeadMid"],
          true,
        );
        statusLightBar(
          xyStatusCanvas,
          250,
          400,
          !inputs["FrameLockHeadBtm"],
          true,
        );

        // Foot Locking Pins
        statusLightBar(
          xyStatusCanvas,
          1150,
          100,
          !inputs["FrameLockFootTop"],
          true,
        );
        statusLightBar(
          xyStatusCanvas,
          1150,
          250,
          !inputs["FrameLockFootMid"],
          true,
        );
        statusLightBar(
          xyStatusCanvas,
          1150,
          400,
          !inputs["FrameLockFootBtm"],
          true,
        );

        statusLight(xyStatusCanvas, 1250, 440, inputs["Light_Curtain"]);

        statusLight(xyStatusCanvas, 30, 400, inputs["Gate_Key"]);
        statusLight(xyStatusCanvas, 30, 350, !inputs["plcFunctional"], true);
        statusLight(xyStatusCanvas, 30, 375, !inputs["estop"], true);

        statusLight(
          xyStatusCanvas,
          1225,
          275,
          inputs["Rotation_Lock_key"],
          true,
        );

        statusLight(xyStatusCanvas, 1225, 485, inputs["endOfTravel_Xp"], true);
        statusLight(xyStatusCanvas, 100, 485, inputs["endOfTravel_Xm"], true);

        statusLight(xyStatusCanvas, 120, 485, inputs["X_Park_OK"]);

        // X-motor status.
        statusLight(xyStatusCanvas, 50, 485, inputs["xFunctional"], true);

        // X transfer.
        statusLight(xyStatusCanvas, 280, 485, inputs["X_Transfer_OK"]);
        statusLight(xyStatusCanvas, 1185, 485, inputs["X_Transfer_OK"]);

        // Y transfers (drawn on loop).
        var x = 100 + loopX / scale;
        statusLight(xyStatusCanvas, x, 440, inputs["Y_Mount_Transfer_OK"]);
        statusLight(xyStatusCanvas, x, 40, inputs["Y_Transfer_OK"]);

        statusLight(xyStatusCanvas, x, 460, inputs["endOfTravel_Ym"], true);
        statusLight(xyStatusCanvas, x, 20, inputs["endOfTravel_Yp"], true);

        // Y-motor status.
        statusLight(xyStatusCanvas, x + 20, 460, inputs["yFunctional"]);

        //
        // Update status lights on Z image.
        // NOTE: Constants come for positions on image.
        //

        statusLight(zStatusCanvas, 485, 150, inputs["Z_End_of_Travel"], true);
        statusLight(zStatusCanvas, 505, 150, inputs["Z_Retracted_1A"]);

        statusLight(zStatusCanvas, 545, 150, inputs["Z_End_of_Travel"], true);
        statusLight(zStatusCanvas, 565, 150, inputs["Z_Extended"]);

        statusLight(zStatusCanvas, 1200, 275, inputs["Z_Fixed_Latched"]);
        statusLight(zStatusCanvas, 1220, 203, inputs["Z_Fixed_Present"]);

        var armBase = zArm / scale;
        statusLight(
          zStatusCanvas,
          armBase + 765,
          135,
          inputs["Latch_Actuator_Top"],
        );
        statusLight(
          zStatusCanvas,
          armBase + 765,
          155,
          inputs["Latch_Actuator_Mid"],
        );
        statusLight(
          zStatusCanvas,
          armBase + 770,
          235,
          inputs["Z_Stage_Present"],
        );
        statusLight(
          zStatusCanvas,
          armBase + 780,
          273,
          inputs["Z_Stage_Latched"],
        );
        statusLight(
          zStatusCanvas,
          armBase + 767,
          305,
          runStatus.states["plcState"] == "Latching",
        );

        // Z-motor status.
        statusLight(
          zStatusCanvas,
          armBase + 50,
          220,
          inputs["zFunctional"],
          true,
        );

        //
        // Draw movement history.
        //

        // If there is a new line segment, the current seek position will be
        // different from the last seek position.
        if (lastX != motorX || lastY != motorY) {
          var x = rescale(
            motorX,
            MIN_X,
            MAX_X,
            MIN_X_POSITION,
            MAX_X_POSITION,
            LINE_OFFSET_X,
          );

          var y = rescale(
            motorY,
            MIN_Y,
            MAX_Y,
            MIN_Y_POSITION,
            MAX_Y_POSITION,
            LINE_OFFSET_Y,
          );

          // Save this location.
          lines.push([x, y]);

          // Get rid of the oldest line segments.
          while (lines.length > LINES + 1) lines.shift();

          var pathCanvas = getCanvas("pathCanvas");

          // Clear canvas.
          pathCanvas.clearRect(0, 0, baseGraphicWidth, baseGraphicHeight);

          // Draw the previous path.
          var previousX = null;
          var previousY = null;
          for (var lineIndex in lines) {
            // Get finishing location for this line.
            var x = lines[lineIndex][0];
            var y = lines[lineIndex][1];

            // If this isn't the first point (we need two points to draw a line
            // segment)...
            if (0 != lineIndex) {
              // Start line segment.
              pathCanvas.beginPath();

              // Make the line.
              pathCanvas.moveTo(previousX, previousY);
              pathCanvas.lineTo(x, y);

              // Calculate the gradient alpha transparency for this line segment.
              var numberOfLines = lines.length - 1;
              var alphaStart = (lineIndex - 1) / numberOfLines;
              var alphaFinish = lineIndex / numberOfLines;

              // Make a gradient color for this line segment.
              // Line color is black with the alpha transparency fading from
              // oldest segment (mostly transparent) to newest (no
              // transparency).
              var gradient = pathCanvas.createLinearGradient(
                previousX,
                previousY,
                x,
                y,
              );
              gradient.addColorStop(
                0,
                "rgba( 139, 69, 19, " + alphaStart + " )",
              );
              gradient.addColorStop(
                1,
                "rgba( 139, 69, 19, " + alphaFinish + " )",
              );
              pathCanvas.lineWidth = 2;
              pathCanvas.strokeStyle = gradient;

              // Draw line segment.
              pathCanvas.stroke();
            }

            // Next starting location is the finishing location of the segment
            // just drawn.
            previousX = x;
            previousY = y;
          }

          // Update histories.
          startingX = lastX;
          startingY = lastY;
          lastX = motorX;
          lastY = motorY;
        }

        var seekCanvas = getCanvas("seekCanvas");

        // If there is a starting point and X/Y is in motion.
        if (
          null !== startingX &&
          null !== startingY &&
          (motorStatus.motor["xMoving"] || motorStatus.motor["yMoving"])
        ) {
          // Clear canvas.
          seekCanvas.clearRect(0, 0, baseGraphicWidth, baseGraphicHeight);

          seekCanvas.beginPath();

          var startX = rescale(
            startingX,
            MIN_X,
            MAX_X,
            MIN_X_POSITION,
            MAX_X_POSITION,
            LINE_OFFSET_X,
          );

          var startY = rescale(
            startingY,
            MIN_Y,
            MAX_Y,
            MIN_Y_POSITION,
            MAX_Y_POSITION,
            LINE_OFFSET_Y,
          );

          var endX = rescale(
            xPosition,
            MIN_X,
            MAX_X,
            MIN_X_POSITION,
            MAX_X_POSITION,
            LINE_OFFSET_X,
          );

          var endY = rescale(
            yPosition,
            MIN_Y,
            MAX_Y,
            MIN_Y_POSITION,
            MAX_Y_POSITION,
            LINE_OFFSET_Y,
          );

          seekCanvas.moveTo(startX, startY);
          seekCanvas.lineTo(endX, endY);

          seekCanvas.strokeStyle = "red";
          seekCanvas.lineWidth = 1;
          seekCanvas.stroke();

          wasMoving = true;
        } else if (wasMoving) {
          seekCanvas.clearRect(0, 0, baseGraphicWidth, baseGraphicHeight);
          wasMoving = false;
        }
      }, // function
    ); // winder.addPeriodicEndCallback
  }; // setupCallback

  var isSetup = false;
  var startSetup = function () {
    // Scaling can take place after machine calibration has been read.
    // So read the calibration and start the setup when we have this data.
    winder.remoteAction("machineCalibration.__dict__", function (data) {
      if (data) {
        machineCaliration = data;
        setupCallback();
      }
    });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Setup periodic callback that will reposition images.  Don't call until
  //   page is fully loaded.
  //-----------------------------------------------------------------------------
  this.initialize = function (scaleParameter) {
    if (scaleParameter) scale = scaleParameter * GRAPHIC_FIT_SCALE;
    else {
      var containerWidth = $("#positionGraphic").width();
      scale =
        containerWidth > 0
          ? (containerWidth / BASE_GRAPHIC_X) * GRAPHIC_FIT_SCALE
          : DEFAULT_SCALE * GRAPHIC_FIT_SCALE;
    }

    if (winder) startSetup();
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Setup images to use scale factor.
  //-----------------------------------------------------------------------------
  var rescale = function () {
    var width = $(this).width() * scale;
    $(this).width(width);

    var ITEMS = ["margin-left", "margin-top", "top"];
    for (index in ITEMS) {
      var item = ITEMS[index];

      var newSize = $(this).css(item);
      var raw = newSize;
      if (newSize) {
        newSize = newSize.replace("px", "");
        if ($.isNumeric(newSize)) {
          newSize = parseFloat(newSize);
          newSize *= scale;

          $(this).css(item, newSize);
        }
      }
    }
    $(this).css("display", "inline");
  };

  modules.load(
    [
      "/Scripts/Winder",
      "/Desktop/Modules/MotorStatus",
      "/Desktop/Modules/RunStatus",
    ],
    function () {
      winder = modules.get("Winder");
      motorStatus = modules.get("MotorStatus");
      runStatus = modules.get("RunStatus");
      inputs = motorStatus.inputs;

      //
      // Load images for X/Y.
      //
      $("<img />")
        .attr("src", "/Desktop/Images/Base.PNG")
        .attr("id", "baseImage")
        .attr("alt", "Front view")
        .load(rescale)
        .appendTo("#sideGraphic");

      $("<canvas />")
        .attr("id", "pathCanvas")
        .addClass("pathCanvas")
        .appendTo("#sideGraphic");

      $("<canvas />")
        .attr("id", "seekCanvas")
        .addClass("seekCanvas")
        .appendTo("#sideGraphic");

      $("<img />")
        .attr("src", "/Desktop/Images/Loop.PNG")
        .attr("id", "loopImage")
        .attr("alt", "Loop view")
        .load(rescale)
        .appendTo("#sideGraphic");

      $("<img />")
        .attr("src", "/Desktop/Images/Head.png")
        .attr("id", "headImage")
        .attr("alt", "Head view")
        .load(rescale)
        .appendTo("#sideGraphic");

      $("<canvas />")
        .attr("id", "xyStatusCanvas")
        .addClass("xyStatusCanvas")
        .appendTo("#sideGraphic");

      //
      // Load images for Z.
      //

      $("<img />")
        .attr("src", "/Desktop/Images/Z_Base.PNG")
        .attr("id", "zBaseImage")
        .attr("alt", "Z-Base view")
        .load(rescale)
        .appendTo("#zGraphic");

      $("<img />")
        .attr("src", "/Desktop/Images/Z_Head.PNG")
        .attr("id", "zHeadImage")
        .attr("alt", "Z-Head view")
        .load(rescale)
        .appendTo("#zGraphic");

      $("<img />")
        .attr("src", "/Desktop/Images/Z_Arm.PNG")
        .attr("id", "zArmImage")
        .attr("alt", "Z-Arm view")
        .load(rescale)
        .appendTo("#zGraphic");

      $("<canvas />")
        .attr("id", "zStatusCanvas")
        .addClass("zStatusCanvas")
        .appendTo("#zGraphic");

      winder.addErrorCallback(function () {
        for (var index in IMAGES_TO_HIDE) {
          var image = IMAGES_TO_HIDE[index];
          $(image).css("display", "none");
        }

        for (var index in IMAGES_TO_BLUR) {
          var image = IMAGES_TO_BLUR[index];
          $(image).css("opacity", "0.75").css("filter", "blur( 10px )");
        }
      });

      winder.addErrorClearCallback(function () {
        for (var index in IMAGES_TO_HIDE) {
          var image = IMAGES_TO_HIDE[index];
          $(image).css("display", "inline");
        }

        for (var index in IMAGES_TO_BLUR) {
          var image = IMAGES_TO_BLUR[index];
          $(image).css("opacity", "1.0").css("filter", "");
        }
      });

      if (scale) startSetup();
    },
  );
} // PositionGraphic
