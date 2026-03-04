function Camera( modules )
{
  var self = this

  // Default velocity is 10%.
  var DEFAULT_VELOCITY = 10

  // How often to update the image from the camera.
  var CAMERA_UPDATE_RATE = 100

  // Dimensions of image from camera.
  var IMAGE_WIDTH  = 640
  var IMAGE_HEIGHT = 480

  var cameraTimer
  var lastCapture = {}

  var page = modules.get( "Page" )
  var winder = modules.get( "Winder" )
  var motorStatus
  var sliders
  var side

  modules.load
  (
    "/Desktop/Modules/MotorStatus",
    function()
    {
      motorStatus = modules.get( "MotorStatus" )
    }
  )

  //---------------------------------------------
  // Sub-pages.
  //---------------------------------------------

  // Motor status.
  page.loadSubPage
  (
    "/Desktop/Modules/MotorStatus",
    "#motorStatusDiv",
    function()
    {
      // Setup copy fields for motor positions.  Allows current motor positions
      // to be copied to input fields.
      var x = new CopyField( "#xPosition", "#xPositionCell" )
      var y = new CopyField( "#yPosition", "#yPositionCell" )
      var z = new CopyField( "#zPosition", "#zPositionCell" )
    }
  )

  // Velocity sliders.
  page.loadSubPage
  (
    "/Desktop/Modules/Sliders",
    "#slidersDiv",
    function()
    {
      sliders = modules.get( "Sliders" )
      sliders.setVelocity( DEFAULT_VELOCITY )

      // Incremental jog.
      page.loadSubPage
      (
        "/Desktop/Modules/IncrementalJog",
        "#increments",
        function()
        {
          var incrementalJog = modules.get( "IncrementalJog" )
          incrementalJog.velocityCallback( sliders.getVelocity )
        }
      )

      // Incremental jog.
      page.loadSubPage
      (
        "/Desktop/Modules/JogJoystick",
        "#jogJoystickDiv",
        function()
        {
          var jogJoystick = modules.get( "JogJoystick" )
          jogJoystick.callbacks
          (
            sliders.getVelocity,
            sliders.getAcceleration,
            sliders.getDeceleration
          )
        }
      )
    }
  )
  //---------------------------------------------
  // Button callbacks.
  //---------------------------------------------

  $( "#triggerStartButton" )
    .click
    (
      function()
      {
        winder.remoteAction( "io.camera.setManualTrigger( True )" )
      }
    )

  $( "#triggerStopButton" )
    .click
    (
      function()
      {
        winder.remoteAction( "io.camera.setManualTrigger( False )" )
      }
    )

  $( "#pixelsPer_mm" )
    .on
    (
      "input",
      function()
      {
        $( "#pixelsPer_mm_Save" ).prop( "disabled", false )
      }
    )

  $( "#pixelsPer_mm_Save" )
    .prop( "disabled", true )
    .click
    (
      function()
      {
        var value = $( "#pixelsPer_mm" ).val()
        winder.remoteAction( "process.cameraCalibration.pixelsPer_mm( " + value + ")" )
        $( "#pixelsPer_mm_Save" ).prop( "disabled", true )
      }
    )

  winder.remoteAction
  (
    "process.cameraCalibration.pixelsPer_mm()",
    function( value )
    {
      $( "#pixelsPer_mm" ).val( value )
    }
  )

  $( "#reset" )
    .click
    (
      function()
      {
        winder.remoteAction( "process.cameraCalibration.reset()" )
      }
    )

  $( "#scanButton" )
    .click
    (
      function()
      {
        var startPin  = parseInt( $( "#startPin" ).val() )
        var endPin    = parseInt( $( "#endPin"   ).val() )
        var spacingX  = parseFloat( $( "#spacingX" ).val() )
        var spacingY  = parseFloat( $( "#spacingY" ).val() )
        var totalPins = parseFloat( $( "#totalPins" ).val() )
        var velocity  = parseFloat( $( "#velocity" ).val() )
        var pixelsPer_mm = parseFloat( $( "#pixelsPer_mm" ).val() )

        var pinDelta = endPin - startPin

        var startX = motorStatus.motor[ "xPosition" ]
        var startY = motorStatus.motor[ "yPosition" ]
        var endX = startX + spacingX * pinDelta
        var endY = startY + spacingY * pinDelta

        var selectedSide = "F"
        if ( 1 == side )
          selectedSide = "B"

        var command =
          "process.startCalibrate( "
          + '"' + selectedSide + '",' +
          + startPin + ", "
          + endPin + ", "
          + totalPins + ","
          + spacingX + ", "
          + spacingY + ", "
          + velocity + " )"

        winder.remoteAction( command )
      }
    )

  $( "#selectPinSeek" )
    .click
    (
      function()
      {
        var x = parseFloat( $( "#selectPinX" ).val() )
        var y = parseFloat( $( "#selectPinY" ).val() )
        var velocity = sliders.getVelocity()

        winder.remoteAction( "process.manualSeekXY( " + x + ", " + y + ", " + velocity + " )"  )
      }
    )

  $( "#selectPinUseCurrent" )
    .click
    (
      function()
      {
        $( "#selectPinX" ).val( parseFloat( motorStatus.motor[ "xPosition" ] ) )
        $( "#selectPinY" ).val( parseFloat( motorStatus.motor[ "yPosition" ] ) )
      }
    )

  $( "#selectPinSave" )
    .click
    (
      function()
      {
        var pin = $( "#selectPin" ).val()
        var x = $( "#selectPinX" ).val()
        var y = $( "#selectPinY" ).val()
        winder.remoteAction
        (
          "process.cameraCalibration.setCalibrationData( " + pin + ", " + x + ", " + y + " )"
        )
      }
    )

  $( "#commitButton" )
    .click
    (
      function()
      {
        var offsetX = $( "#offsetX" ).val()
        var offsetY = $( "#offsetY" ).val()

        winder.remoteAction
        (
          'process.commitCalibration( ' + side + ', ' + offsetX + ',' + offsetY + ' )'
        )
      }
    )

  $( "#nominalPinSeek" )
    .click
    (
      function()
      {
        var pin = $( "#startPin" ).val()
        var velocity = sliders.getVelocity()
        var sideText = "F"
        if ( 1 == side )
          sideText = "B"

        winder.remoteAction( 'process.seekPinNominal( "' + sideText + pin + '", ' + velocity + ' )' )
      }
    )

  $( "#centerButton" )
    .click
    (
      function()
      {
        var velocity = sliders.getVelocity()
        winder.remoteAction( 'process.cameraSeekCenter( ' + velocity + ' )' )
      }
    )

  //---------------------------------------------

  winder.addPeriodicDisplay( "io.camera.cameraResultStatus.get()", "#cameraResult", lastCapture, "status" )
  winder.addPeriodicDisplay( "io.camera.cameraResultScore.get()", "#cameraScore", lastCapture, "score" )
  winder.addPeriodicDisplay( "io.camera.cameraResultX.get()", "#cameraX", lastCapture, "x" )
  winder.addPeriodicDisplay( "io.camera.cameraResultY.get()", "#cameraY", lastCapture, "y" )

  //---------------------------------------------------------------------------
  // Uses:
  //   Draw a line on the specified canvas.
  // Input:
  //   canvas - Canvas to place line.
  //   x1 - X coordinate of starting location.
  //   y1 - Y coordinate of starting location.
  //   x2 - X coordinate of end location.
  //   y2 - Y coordinate of end location.
  //---------------------------------------------------------------------------
  function line( canvas, x1, y1, x2, y2 )
  {
    if ( ( x1 % 2 ) > 0 )
      x1 += 0.5

    if ( ( y1 % 2 ) > 0 )
      y1 += 0.5

    if ( ( x2 % 2 ) > 0 )
      x2 += 0.5

    if ( ( y2 % 2 ) > 0 )
      y2 += 0.5

    canvas.beginPath()
    canvas.strokeStyle = "red"
    canvas.moveTo( x1, y1 )
    canvas.lineTo( x2, y2 )
    canvas.stroke()
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Display crosshairs on camera image overlay at the given X/Y position.
  // Input:
  //   x - X location in pixels.
  //   y - Y location in pixels.
  //   length - Length of crosshairs.
  //---------------------------------------------------------------------------
  function crosshairs( canvas, x, y, length )
  {
    x = Math.round( x )
    y = Math.round( y )
    length = Math.round( length )
    line( canvas, x - length, y, x + length, y )
    line( canvas, x, y - length, x, y + length )
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Update function for image from camera.
  //---------------------------------------------------------------------------
  var cameraURL
  function cameraUpdateFunction()
  {
    var url = cameraURL + "?random=" + Math.floor( Math.random() * 0xFFFFFFFF )

    $( "#cameraImage" )
      .attr( "src", url )
      .bind
      (
        "load",
        function()
        {
          var canvas = getCanvas( "cameraCanvas" )
          canvas.clearRect( 0, 0, IMAGE_WIDTH, IMAGE_HEIGHT )

          canvas.drawImage(this, 0, 0, IMAGE_WIDTH, IMAGE_HEIGHT);

          canvas.lineWidth = 1
          canvas.strokeStyle = "black"
          crosshairs( canvas, IMAGE_WIDTH / 2, IMAGE_HEIGHT / 2, 10 )

          canvas.strokeStyle = "Magenta"
          crosshairs( canvas, lastCapture[ "x" ], lastCapture[ "y" ], 10 )
        }
      )
  }


  //---------------------------------------------------------------------------
  // Uses:
  //   Round to specified number of decimal places.
  // Input:
  //   value - Value to round.
  //   decimals - Number of decimal places to round.
  // Output:
  //   Rounded value.
  //---------------------------------------------------------------------------
  function round( value, decimals )
  {
    var multiplier = Math.pow( 10, decimals )
    return Math.round( value * multiplier ) / multiplier
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Function to load the URL of the camera's last captured image.
  //   This URL is configured in the control software.
  //---------------------------------------------------------------------------
  function loadCameraURL()
  {
    winder.remoteAction
    (
      "process.getCameraImageURL()",
      function( url )
      {
        cameraURL = url
        if ( cameraTimer )
        {
          clearInterval( cameraTimer )
          cameraTimer = null
        }

        cameraTimer = setInterval( cameraUpdateFunction, CAMERA_UPDATE_RATE )
      }
    )
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get the APA side facing the front of the machine.
  //---------------------------------------------------------------------------
  function loadSide()
  {
    winder.remoteAction
    (
      "process.getAPA_Side()",
      function( data )
      {
        side = data
        var sideText = "N/A"
        if ( -1 == side )
          disableSelectState()
        else
        {
          setSelectState( 0 )
          sideText = "Front"
          if ( 1 == side )
            sideText = "Back"

        }
        $( "#apaSide" ).text( sideText )
      }
    )
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get the APA side facing the front of the machine.
  //---------------------------------------------------------------------------
  function loadLayer()
  {
    winder.remoteAction
    (
      "process.getRecipeLayer()",
      function( layer )
      {
        if ( null == layer )
          layer = "N/A"

        $( "#apaLayer" ).text( layer )
      }
    )
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get a canvas context by name.
  //---------------------------------------------------------------------------
  function getCanvas( canvasName )
  {
    var canvas = document.getElementById( canvasName )
    var context

    if ( canvas )
      context = canvas.getContext( "2d" )

    return context
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Compare function used to see if two capture FIFOs differ.
  // Input:
  //   a - First FIFO to compare.
  //   b - Second FIFO to compare.
  // Returns:
  //   True if the FIFOs differ, false if they are the same.
  //---------------------------------------------------------------------------
  function isCaptureFIFO_Different( a, b )
  {
    var isDifferent = false

    isDifferent |= ! ( a instanceof Array )
    isDifferent |= ! ( b instanceof Array )

    if ( ! isDifferent )
      isDifferent |= ( a.length != b.length )

    if ( ! isDifferent )
    {
      for ( var index = 0; index < a.length; index += 1 )
      {
        var rowA = a[ index ]
        var rowB = b[ index ]

        for ( var key in rowA )
          isDifferent |= rowA[ key ] != rowB[ key ]
      }
    }

    return isDifferent
  }

  // Shutdown/restart function to stop/restart camera updates.
  modules
    .registerShutdownCallback
    (
      function()
      {
        disableSelectState()
        clearInterval( cameraTimer )
        cameraTimer = null
      }
    )
    .registerRestoreCallback
    (
      function()
      {
        loadCameraURL()
        loadSide()
        loadLayer()
      }
    )

  // Filter table object with columns for the log file.
  var filteredTable =
      new FilteredTable
      (
        [ "Motor X", "Motor Y", "Status", "Match Level", "Camera X", "Camera Y" ],
        [ false, false, false, false, false, false ],
        []
      )

  var oldData = null

  var columnNames = [ "Side", "Pin",  "Motor X", "Motor Y", "Ok?", "Match"   ]
  var filters     = [ false,   false, false,     false,     true,     false     ]
  var widths      = [ "15%",  "15%",  "20%",     "20%",     "15%",    "15%"     ]
  var filteredTable = new FilteredTable( columnNames, filters, widths )

  // Callback when a row on the calibration table is clicked.
  // The information from the row is put in the Select Pin table.
  filteredTable.setRowCallback
  (
    function( row )
    {
      var rowData = oldData[ row ]
      $( "#selectPin"  ).val( rowData[ "Pin" ] )
      $( "#selectPinX" ).val( round( rowData[ "MotorX_Corrected" ], 2 ) )
      $( "#selectPinY" ).val( round( rowData[ "MotorY_Corrected" ], 2 ) )
      $( "#selectMotorX"  ).text( round( rowData[ "MotorX" ], 2 ) )
      $( "#selectMotorY"  ).text( round( rowData[ "MotorY" ], 2 ) )
      $( "#selectCameraX" ).text( round( rowData[ "CameraX" ], 2 ) )
      $( "#selectCameraY" ).text( round( rowData[ "CameraY" ], 2 ) )
    }
  )

  winder.addPeriodicCallback
  (
    "process.cameraCalibration.getCalibrationData()",
    function( data )
    {
      if ( isCaptureFIFO_Different( data, oldData ) )
      {
        oldData = data

        var cleanData = []
        for ( var rowIndex in data )
        {
          var row = data[ rowIndex ]
          cleanData.push
          (
            [
              row.Side,
              row.Pin,
              round( row.MotorX_Corrected, 2 ),
              round( row.MotorY_Corrected, 2 ),
              row.Status,
              round( row.MatchLevel, 0 ),
              round( row.CameraX, 2 ),
              round( row.CameraY, 2 ),
            ]
          )
        }

        filteredTable.loadFromArray( cleanData )
        filteredTable.display( "#calibrationTable" )
      }

    }
  )

  var ENABLE_STATES =
  [
    {
      TL : true,
      T  : false,
      TR : true,
      L  : false,
      GO : false,
      R  : false,
      BL : true,
      B  : false,
      BR : true
    },

    {
      TL : false,
      T  : true,
      TR : false,
      L  : true,
      GO : false,
      R  : true,
      BL : false,
      B  : true,
      BR : false
    },

    {
      TL : false,
      T  : false,
      TR : false,
      L  : false,
      GO : true,
      R  : false,
      BL : false,
      B  : false,
      BR : false
    }
  ]

  var OUTER =
  [
    "#TL",
    "#TR",
    "#BL",
    "#BR",
    "#T",
    "#L",
    "#R",
    "#B"
  ]

  var CORNERS =
  [
    [ "#TL", "TL" ],
    [ "#TR", "TR" ],
    [ "#BL", "BL" ],
    [ "#BR", "BR" ]
  ]

  var EDGES =
  [
    [ "#T", "T" ],
    [ "#L", "L" ],
    [ "#R", "R" ],
    [ "#B", "B" ]
  ]

  // Starting corner.
  var selectedCorner = null

  //---------------------------------------------------------------------------
  // Uses:
  //   Enable/disable select state buttons based on state.
  // Input:
  //   state - That to place buttons (0-2).
  //---------------------------------------------------------------------------
  var currentState
  function setSelectState( state )
  {
    currentState = state
    for ( var tag in ENABLE_STATES[ state ] )
    {
      var enable = ENABLE_STATES[ state ][ tag ]
      $( "#" + tag ).prop( "disabled", ! enable )
    }
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Disable all state select buttons.
  //---------------------------------------------------------------------------
  function disableSelectState()
  {
    for ( var tag in ENABLE_STATES[ 0 ] )
      $( "#" + tag ).prop( "disabled", true )
  }

  for ( var index in CORNERS )
  {
    let corner = CORNERS[ index ]
    $( corner[ 0 ] )
      .click
      (
        function()
        {
          $( corner[ 0 ] ).attr( "class", "selected" )
          selectedCorner = corner[ 1 ]
          setSelectState( 1 )
        }
      )
  }

  // Setup the edge button callbacks.
  for ( var index in EDGES )
  {
    let edge = EDGES[ index ]
    $( edge[ 0 ] )
      .click
      (
        function()
        {
          var selectedEdge = edge[ 1 ]
          var otherSelection = selectedCorner.replace( selectedEdge, "" )

          var DIRECTIONS =
          {
            L: "R",
            R: "L",
            T: "B",
            B: "T"
          }

          var direction = DIRECTIONS[ otherSelection ]

          var scanDirection = otherSelection + direction

          // Starting/ending corner of scan.
          var startCorner = selectedEdge + otherSelection
          var endCorner = selectedEdge + direction

          // Fetch the layer geometry.
          winder.remoteAction
          (
            "process.getLayerPinGeometry()",
            function( data )
            {
              var front     = data[ 0 ]
              var back      = data[ 1 ]
              var totalPins = data[ 2 ]

              var startPin         = front[ startCorner ][ 0 ]
              var endPin           = front[ endCorner   ][ 0 ]
              var deltaX           = front[ startCorner ][ 1 ]
              var deltaY           = front[ startCorner ][ 2 ]
              var offsetX          = round( front[ startCorner ][ 3 ], 13 )
              var offsetY          = round( front[ startCorner ][ 4 ], 13 )
              var oppositeStartPin = back[ startCorner ][ 0 ]
              var oppositeEndPin   = back[ endCorner   ][ 0 ]

              // Fill in the parameters for the scan with information from
              // geometry.
              $( "#startPin"  ).val( startPin )
              $( "#endPin"    ).val( endPin )
              $( "#totalPins" ).val( totalPins )
              $( "#spacingX"  ).val( deltaX )
              $( "#spacingY"  ).val( deltaY )
              $( "#offsetX"   ).val( offsetX )
              $( "#offsetY"   ).val( offsetY )
              $( "#oppositeStartPin" ).val( oppositeStartPin )
              $( "#oppositeEndPin"   ).val( oppositeEndPin )
            }
          )

          var ARROWS =
          {
            LR: "&#8594;",
            RL: "&#8592;",
            TB: "&#8595;",
            BT: "&#8593;"
          }

          for ( var item in OUTER )
            if ( ( OUTER[ item ] != ( "#" + selectedEdge ) )
              && ( OUTER[ item ] != ( "#" + selectedCorner ) ) )
            {
              $( OUTER[ item ] ).attr( "class", "notSelected" )
            }

          $( edge[ 0 ] ).html( ARROWS[ scanDirection ] )

          setSelectState( 2 )
        }
      )
  }

  $( "#GO" )
    .click
    (
      function()
      {
        $( "#TL" ).attr( "class", "" )
        $( "#TR" ).attr( "class", "" )
        $( "#BL" ).attr( "class", "" )
        $( "#BR" ).attr( "class", "" )

        $( "#T" ).html( "&#8660;" ).attr( "class", "" )
        $( "#L" ).html( "&#8661;" ).attr( "class", "" )
        $( "#R" ).html( "&#8661;" ).attr( "class", "" )
        $( "#B" ).html( "&#8660;" ).attr( "class", "" )

        setSelectState( 0 )
      }
    )

  //---------------------------------------------
  // Construction
  //---------------------------------------------

  setSelectState( 0 )
  loadCameraURL()
  loadSide()
  loadLayer()
}
