function Jog(modules) {
  var self = this;
  var winder = modules.get("Winder");
  var page = modules.get("Page");
  var motorStatus;
  modules.load("/Desktop/Modules/MotorStatus", function () {
    motorStatus = modules.get("MotorStatus");
  });
  var sliders;

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for reset button.
  //-----------------------------------------------------------------------------
  this.reset = function () {
    winder.remoteAction("process.acknowledgeError()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for servo disable button.
  //-----------------------------------------------------------------------------
  this.servoDisable = function () {
    winder.remoteAction("process.servoDisable()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start X/Y axis seek.
  //-----------------------------------------------------------------------------
  this.seekXY = function (x, y) {
    var velocity = this.getVelocity();
    var acceleration = this.getAcceleration();
    var deceleration = this.getDeceleration();
    winder.remoteAction(
      "process.manualSeekXY(" +
        x +
        "," +
        y +
        "," +
        velocity +
        "," +
        acceleration +
        "," +
        deceleration +
        ")"
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to seek from one of the seek sets.
  // Input:

  //-----------------------------------------------------------------------------
  this.seekXY_Set = function (setName) {
    var x = $("#seekX_" + setName).val();
    var y = $("#seekY_" + setName).val();
    this.seekXY(x, y);
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Seek a point in machine geometry.
  // Input:
  //   x - Name of geometry variable that defines x position.
  //   y - Name of geometry variable that defines y position.
  //-----------------------------------------------------------------------------
  this.seekLocation = function (x, y) {
    var velocity = this.getVelocity();

    if (x) x = "process.apa._gCodeHandler." + x;
    else x = "None";

    if (y) y = "process.apa._gCodeHandler." + y;
    else y = "None";

    winder.remoteAction(
      "process.manualSeekXY( " + x + ", " + y + "," + velocity + ")"
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start Z axis seek.
  //-----------------------------------------------------------------------------
  this.seekZ = function (position) {
    var z = position;
    if (null == z) z = $("#seekZ").val();

    var velocity = this.getVelocity();
    winder.remoteAction("process.manualSeekZ(" + z + "," + velocity + ")");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop Z axis jogging.
  //-----------------------------------------------------------------------------
  this.jogZ_Stop = function () {
    winder.remoteAction("process.jogZ( 0 )");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start Z axis jogging.
  // Input:
  //   direction - Direction (1,-1, 0) of jog.
  //-----------------------------------------------------------------------------
  this.jogZ_Start = function (direction) {
    var velocity = this.getVelocity() * direction;
    winder.remoteAction("process.jogZ(" + velocity + ")");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully retract Z axis.
  //-----------------------------------------------------------------------------
  this.zRetract = function () {
    var velocity = this.getVelocity();
    winder.remoteAction("process.manualSeekZ( 0, " + velocity + " )");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully extend Z axis.
  //-----------------------------------------------------------------------------
  this.zExtend = function () {
    var velocity = this.getVelocity();
    var position = $("#extendedPosition").val();
    winder.remoteAction(
      "process.manualSeekZ( " + position + ", " + velocity + " )"
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Partly extend Z axis.
  //-----------------------------------------------------------------------------
  this.zMid = function () {
    var velocity = this.getVelocity();
    var position = $("#extendedPosition").val() / 2;
    winder.remoteAction(
      "process.manualSeekZ( " + position + ", " + velocity + " )"
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Run a latching operation.
  //-----------------------------------------------------------------------------
  this.latch = function () {
    winder.remoteAction("io.plcLogic.move_latch()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch homing sequence.
  //-----------------------------------------------------------------------------
  this.latchHome = function () {
    winder.remoteAction("io.plcLogic.latchHome()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch unlock.
  //-----------------------------------------------------------------------------
  this.latchUnlock = function () {
    winder.remoteAction("io.plcLogic.latchUnlock()");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the position of the head.
  //-----------------------------------------------------------------------------
  this.headPosition = function (position) {
    var velocity = this.getVelocity();
    winder.remoteAction(
      "process.manualHeadPosition( " + position + "," + velocity + " )"
    );
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to seek to specified pin.
  //-----------------------------------------------------------------------------
  this.seekPin = function () {
    var pin = $("#seekPin").val().toUpperCase();
    var velocity = this.getVelocity();
    winder.remoteAction("process.seekPin( '" + pin + "', " + velocity + " )");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to set the anchor point.
  //-----------------------------------------------------------------------------
  this.setAnchor = function () {
    var pin = $("#anchorPin").val().toUpperCase();

    var parameters = '"' + pin + '"';
    if (pin.indexOf(",") >= 0) {
      var pins = pin.split(",");
      parameters = '"' + pins[0] + '", "' + pins[1] + '"';
    }

    winder.remoteAction("process.setAnchorPoint( " + parameters + " )");
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to set the anchor point.
  //-----------------------------------------------------------------------------
  this.executeGCode = function () {
    $("#gExecutionCodeStatus").html("Request G-Code execution...");

    var gCode = $("#manualGCode").val();
    //UPDATED TO CHANGE MANUAL GCODE TO UPPERCASE - deactivated as update was made to Jog.html
    //gCode = gCode.toUpperCase()
    winder.remoteAction(
      'process.executeG_CodeLine( "' + gCode + '" )',
      function (data) {
        if (!data) $("#gExecutionCodeStatus").html("Executed with no errors.");
        else
          $("#gExecutionCodeStatus").html("Error interpreting line: " + data);
      }
    );
  };

  page.loadSubPage(
    "/Desktop/Modules/PositionGraphic",
    "#positionGraphicDiv",
    function () {
      var positionGraphic = modules.get("PositionGraphic");
      positionGraphic.initialize(0.7, motorStatus);
    }
  );

  page.loadSubPage(
    "/Desktop/Modules/MotorStatus",
    "#motorStatusDiv",
    function () {
      // Setup copy fields for motor positions.  Allows current motor positions
      // to be copied to input fields.
      var x = new CopyField("#xPosition", "#xPositionCell");
      var y = new CopyField("#yPosition", "#yPositionCell");
      var z = new CopyField("#zPosition", "#zPositionCell");
    }
  );

  // Velocity sliders.
  page.loadSubPage("/Desktop/Modules/Sliders", "#slidersDiv", function () {
    sliders = modules.get("Sliders");

    // Incremental jog.
    page.loadSubPage(
      "/Desktop/Modules/IncrementalJog",
      "#increments",
      function () {
        var incrementalJog = modules.get("IncrementalJog");
        incrementalJog.velocityCallback(sliders.getVelocity);
      }
    );

    // Jog joystick.
    page.loadSubPage(
      "/Desktop/Modules/JogJoystick",
      "#jogJoystickDiv",
      function () {
        var jogJoystick = modules.get("JogJoystick");
        jogJoystick.callbacks(
          sliders.getVelocity,
          sliders.getAcceleration,
          sliders.getDeceleration
        );
      }
    );
  });

  // Fetch fully extended position from machine calibration.
  winder.remoteAction("machineCalibration.zBack", function (data) {
    $("#extendedPosition").val(data);
  });

  window["jog"] = this;
}
