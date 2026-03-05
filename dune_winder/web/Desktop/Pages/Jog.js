function Jog(modules) {
  var self = this;
  var winder = modules.get("Winder");
  var page = modules.get("Page");
  var commands = window.CommandCatalog;
  var call = function (commandName, args, callback) {
    winder.call(commandName, args, function (response) {
      if (response && response.ok) {
        if (callback) callback(response.data, null);
      } else {
        if (callback) callback(null, response);
      }
    });
  };
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
    call(commands.process.acknowledgeError, {});
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for servo disable button.
  //-----------------------------------------------------------------------------
  this.servoDisable = function () {
    call(commands.process.servoDisable, {});
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start X/Y axis seek.
  //-----------------------------------------------------------------------------
  this.seekXY = function (x, y) {
    var velocity = this.getVelocity();
    var acceleration = this.getAcceleration();
    var deceleration = this.getDeceleration();
    call(commands.process.manualSeekXY, {
      x: x,
      y: y,
      velocity: velocity,
      acceleration: acceleration,
      deceleration: deceleration,
    });
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
    call(commands.process.manualSeekXYNamed, {
      x_name: x || null,
      y_name: y || null,
      velocity: velocity,
    });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start Z axis seek.
  //-----------------------------------------------------------------------------
  this.seekZ = function (position) {
    var z = position;
    if (null == z) z = $("#seekZ").val();

    var velocity = this.getVelocity();
    call(commands.process.manualSeekZ, { position: z, velocity: velocity });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop Z axis jogging.
  //-----------------------------------------------------------------------------
  this.jogZ_Stop = function () {
    call(commands.process.jogZ, { velocity: 0 });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start Z axis jogging.
  // Input:
  //   direction - Direction (1,-1, 0) of jog.
  //-----------------------------------------------------------------------------
  this.jogZ_Start = function (direction) {
    var velocity = this.getVelocity() * direction;
    call(commands.process.jogZ, { velocity: velocity });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully retract Z axis.
  //-----------------------------------------------------------------------------
  this.zRetract = function () {
    var velocity = this.getVelocity();
    call(commands.process.manualSeekZ, { position: 0, velocity: velocity });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully extend Z axis.
  //-----------------------------------------------------------------------------
  this.zExtend = function () {
    var velocity = this.getVelocity();
    var position = $("#extendedPosition").val();
    call(commands.process.manualSeekZ, { position: position, velocity: velocity });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Partly extend Z axis.
  //-----------------------------------------------------------------------------
  this.zMid = function () {
    var velocity = this.getVelocity();
    var position = $("#extendedPosition").val() / 2;
    call(commands.process.manualSeekZ, { position: position, velocity: velocity });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Run a latching operation.
  //-----------------------------------------------------------------------------
  this.latch = function () {
    call(commands.io.moveLatch, {});
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch homing sequence.
  //-----------------------------------------------------------------------------
  this.latchHome = function () {
    call(commands.io.latchHome, {});
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch unlock.
  //-----------------------------------------------------------------------------
  this.latchUnlock = function () {
    call(commands.io.latchUnlock, {});
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the position of the head.
  //-----------------------------------------------------------------------------
  this.headPosition = function (position) {
    var velocity = this.getVelocity();
    call(commands.process.manualHeadPosition, {
      position: position,
      velocity: velocity,
    });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to seek to specified pin.
  //-----------------------------------------------------------------------------
  this.seekPin = function () {
    var pin = $("#seekPin").val().toUpperCase();
    var velocity = this.getVelocity();
    call(commands.process.seekPin, { pin: pin, velocity: velocity });
  };

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to set the anchor point.
  //-----------------------------------------------------------------------------
  this.setAnchor = function () {
    var pin = $("#anchorPin").val().toUpperCase();

    var args = { pin_a: pin };
    if (pin.indexOf(",") >= 0) {
      var pins = pin.split(",");
      args = { pin_a: pins[0], pin_b: pins[1] };
    }
    call(commands.process.setAnchorPoint, args);
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
    call(commands.process.executeGCodeLine, { line: gCode }, function (data, error) {
      if (error) {
        $("#gExecutionCodeStatus").html("Error interpreting line: " + error.error.message);
      } else if (!data) {
        $("#gExecutionCodeStatus").html("Executed with no errors.");
      } else {
        $("#gExecutionCodeStatus").html("Error interpreting line: " + data);
      }
    });
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
  call(commands.machine.getZBack, {}, function (data) {
    $("#extendedPosition").val(data);
  });

  window["jog"] = this;
}
