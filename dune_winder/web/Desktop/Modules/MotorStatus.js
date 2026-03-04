function MotorStatus( modules )
{
  // Pointer to self.
  var self = this

  // Public motor status data.
  this.motor = {}
  this.inputs = {}
  this.uiSnapshot = null

  var winder = modules.get( "Winder" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Replace the contents of an object while preserving its identity so other
  //   modules can safely keep a reference to it.
  //-----------------------------------------------------------------------------
  var replaceMap = function( target, source )
  {
    for ( var key in target )
      if ( ! source.hasOwnProperty( key ) )
        delete target[ key ]

    for ( var key in source )
      target[ key ] = source[ key ]
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Copy x and y positions to clipboard in CSV form for spreadsheet pasting.
  //-----------------------------------------------------------------------------
  var copyXYToClipboard = function()
  {
    var sanitize = function( value )
    {
      return String( value ).replace( /[\r\n\t]+/g, " " ).trim()
    }
    var x = sanitize( $( "#xPosition" ).text() )
    var y = sanitize( $( "#yPosition" ).text() )
    var plainText = x + "\t" + y
    var onSuccess = function()
    {
      $( "#motorStatusCopyStatus" ).text( "Copied X/Y" )
    }
    var onFailure = function()
    {
      $( "#motorStatusCopyStatus" ).text( "Copy failed" )
    }

    if ( navigator.clipboard && navigator.clipboard.writeText )
    {
      navigator.clipboard.writeText( plainText ).then( onSuccess, onFailure )
      return
    }

    // Compatibility fallback for older browser engines.
    var textArea = document.createElement( "textarea" )
    textArea.value = plainText
    textArea.setAttribute( "readonly", "" )
    textArea.style.position = "fixed"
    textArea.style.opacity = "0"
    document.body.appendChild( textArea )
    textArea.select()

    try
    {
      var didCopy = document.execCommand( "copy" )
      if ( didCopy )
        onSuccess()
      else
        onFailure()
    }
    catch ( error )
    {
      onFailure()
    }
    finally
    {
      document.body.removeChild( textArea )
    }
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Read configuration variables related to motor limits. (Private)
  //-----------------------------------------------------------------------------
  var readConfig = function()
  {
    winder.remoteAction
    (
      'configuration.get( "maxAcceleration" )',
      function( data )
      {
        self.motor[ "maxAcceleration" ] = parseFloat( data )
      }
    )

    winder.remoteAction
    (
      'configuration.get( "maxDeceleration" )',
      function( data )
      {
        self.motor[ "maxDeceleration" ] = parseFloat( data )
      }
    )

    winder.remoteAction
    (
      'configuration.get( "maxVelocity" )',
      function( data )
      {
        self.motor[ "maxVelocity" ] = parseFloat( data )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Setup progress bars.  (Private)
  // Input:
  //   axis - The axis to setup.
  // Notes:
  //   Function exists to avoid needing 'let' operator.
  //-----------------------------------------------------------------------------
  var barSetup = function( axis )
  {
    winder.addPeriodicEndCallback
    (
      function()
      {
        var isFunctional = self.motor[ axis + "Functional" ]
        var isMoving = self.motor[ axis + "Moving" ]
        var rawVelocity = self.motor[ axis + "Velocity" ]
        var acceleration = self.motor[ axis + "Acceleration" ]
        var topAcceleration = self.motor[ "maxAcceleration" ]
        var direction = ( acceleration < 0 ) ^ ( rawVelocity < 0 )
        if ( direction )
          topAcceleration = self.motor[ "maxDeceleration" ]

        topAcceleration *= Math.sign( acceleration )

        if ( ! isFunctional )
          $( "#" + axis + "Label" ).addClass( "inError" )
        else
        {
          $( "#" + axis + "Label" ).removeClass( "inError" )
          if ( isMoving )
            $( "#" + axis + "Label" ).addClass( "inMotion" )
          else
            $( "#" + axis + "Label" ).removeClass( "inMotion" )
        }

        var level = 0
        if ( topAcceleration != 0 )
        {
          level = acceleration / topAcceleration
          level = Math.min( level, 1.0 )
        }

        if ( ! isMoving )
          level = 0

        level *= $( "#" + axis + "AccelerationBar" ).parent().width() + 10
        $( "#" + axis + "AccelerationBar" ).width( "" + Math.round( level ) + "px" )

        var desiredPosition = self.motor[ axis + "DesiredPosition" ]
        var position = self.motor[ axis + "Position" ]
        var startPosition = self.motor[ axis + "SeekStartPosition" ]

        level = Math.abs( position - startPosition ) / Math.abs( desiredPosition - startPosition )
        level = Math.min( level, 1.0 )

        if ( ! isMoving )
          level = 1

        level *= $( "#" + axis + "PositionBar" ).parent().width() + 10
        $( "#" + axis + "PositionBar" ).width( "" + Math.round( level ) + "px" )

        var maxVelocity = self.motor[ "maxVelocity" ]
        var velocity = Math.abs( self.motor[ axis + "Velocity" ] )

        var level = 0
        if ( maxVelocity != 0 )
        {
          level = velocity / maxVelocity
          level = Math.min( level, 1.0 )
        }

        if ( ! isMoving )
          level = 0

        level *= $( "#" + axis + "VelocityBar" ).parent().width() + 10
        $( "#" + axis + "VelocityBar" ).width( "" + Math.round( level ) + "px" )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Format a number with request number of decimal places.  (Private)
  // Input:
  //   data - Number to format.
  //   decimals - Number of decimal places.
  // Output:
  //   Number rounded to the requested decimal places.
  //-----------------------------------------------------------------------------
  var formatFunction = function( data, decimals )
  {
    if ( $.isNumeric( data ) )
    {

      var multiplier = Math.pow( 10, decimals )
      data = Math.round( data * multiplier ) / multiplier
    }
    else
      data = "-"

    return data
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Display a formatted motor value and keep the existing motorStatus.motor
  //   structure current for other modules.
  //-----------------------------------------------------------------------------
  var updateAxisFromSnapshot = function( axis, axisSnapshot )
  {
    var functional = null
    var moving = null
    var desiredPosition = null
    var position = null
    var velocity = null
    var acceleration = null
    var seekStartPosition = null

    if ( axisSnapshot )
    {
      functional = axisSnapshot[ "functional" ]
      moving = axisSnapshot[ "moving" ]
      desiredPosition = axisSnapshot[ "desiredPosition" ]
      position = axisSnapshot[ "position" ]
      velocity = axisSnapshot[ "velocity" ]
      acceleration = axisSnapshot[ "acceleration" ]
      seekStartPosition = axisSnapshot[ "seekStartPosition" ]
    }

    self.motor[ axis + "Functional" ] = functional
    self.motor[ axis + "Moving" ] = moving
    self.motor[ axis + "DesiredPosition" ] = desiredPosition
    self.motor[ axis + "Position" ] = position
    self.motor[ axis + "Velocity" ] = velocity
    self.motor[ axis + "Acceleration" ] = acceleration
    self.motor[ axis + "SeekStartPosition" ] = seekStartPosition

    $( "#" + axis + "DesiredPosition" ).text( formatFunction( desiredPosition, 1 ) )
    $( "#" + axis + "Position" ).text( formatFunction( position, 1 ) )
    $( "#" + axis + "Velocity" ).text( formatFunction( velocity, 2 ) )
    $( "#" + axis + "Acceleration" ).text( formatFunction( acceleration, 2 ) )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Refresh all hot-path UI state from a single server-side snapshot.
  //-----------------------------------------------------------------------------
  var updateFromSnapshot = function( snapshot )
  {
    var inputSnapshot = {}
    var axes = null

    self.uiSnapshot = snapshot

    if ( snapshot )
    {
      axes = snapshot[ "axes" ]
      self.motor[ "headSide" ] = snapshot[ "headSide" ]
      self.motor[ "headAngle" ] = snapshot[ "headAngle" ]
      if ( snapshot[ "inputs" ] )
        inputSnapshot = snapshot[ "inputs" ]

      inputSnapshot[ "plcFunctional" ] = snapshot[ "plcNotFunctional" ]
      inputSnapshot[ "plcNotFunctional" ] = snapshot[ "plcNotFunctional" ]
    }
    else
    {
      self.motor[ "headSide" ] = null
      self.motor[ "headAngle" ] = null
      inputSnapshot[ "plcFunctional" ] = null
      inputSnapshot[ "plcNotFunctional" ] = null
    }

    if ( axes )
    {
      updateAxisFromSnapshot( "x", axes[ "x" ] )
      updateAxisFromSnapshot( "y", axes[ "y" ] )
      updateAxisFromSnapshot( "z", axes[ "z" ] )

      inputSnapshot[ "xFunctional" ] = axes[ "x" ][ "functional" ]
      inputSnapshot[ "yFunctional" ] = axes[ "y" ][ "functional" ]
      inputSnapshot[ "zFunctional" ] = axes[ "z" ][ "functional" ]
    }
    else
    {
      updateAxisFromSnapshot( "x", null )
      updateAxisFromSnapshot( "y", null )
      updateAxisFromSnapshot( "z", null )

      inputSnapshot[ "xFunctional" ] = null
      inputSnapshot[ "yFunctional" ] = null
      inputSnapshot[ "zFunctional" ] = null
    }

    replaceMap( self.inputs, inputSnapshot )
  }

  //-----------------------------------------------------------------------------
  // Constructor
  //-----------------------------------------------------------------------------

  winder.addPeriodicCallback
  (
    "process.getUiSnapshot()",
    updateFromSnapshot
  )

  var AXIES = [ "x", "y", "z" ]
  for ( var index in AXIES )
  {
    var axis = AXIES[ index ]

    barSetup( axis )
  }

  readConfig()
  winder.addErrorClearCallback( readConfig )

  $( "#motorStatusCopyXYButton" ).click( copyXYToClipboard )

}
