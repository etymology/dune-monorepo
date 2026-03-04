function Jog( modules )
{
  var self = this
  window[ "jog" ] = this

  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )

  var MIN_VELOCITY = 1.0
  var maxVelocity

  var MIN_ACCELERATION = 1.0
  var maxAcceleration
  var maxDeceleration

  var extendedPosition

  var speedLimit = 0.1

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to set new jog speed.
  // Input:
  //   newSpeed - New jog speedLimit (0-1).
  //-----------------------------------------------------------------------------
  this.setSpeed = function( newSpeed )
  {
    speedLimit = newSpeed
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start X/Y axis jog.
  // Input:
  //   x - Direction (1,-1, 0) for x-axis.
  //   y - Direction (1,-1, 0) for y-axis.
  //-----------------------------------------------------------------------------
  this.jogXY_Start = function( x, y )
  {
    // Convert direction to velocity.
    var velocity = maxVelocity * speedLimit
    x *= velocity
    y *= velocity

    // When both velocities are the same, calculate the maximum linear velocity
    // and use that.
    if ( ( 0 != x )
      && ( 0 != y )
      && ( Math.abs( x ) == Math.abs( y ) ) )
    {
      velocity = Math.sqrt( x * x / 2.0 )

      if ( x < 0 )
        x = -velocity
      else
        x = velocity

      if ( y < 0 )
        y = -velocity
      else
        y = velocity
    }

    var acceleration = maxAcceleration
    var deceleration = maxDeceleration

    winder.remoteAction
    (
      "process.jogXY(" + x + "," + y + "," + acceleration + "," + deceleration + ")"
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop X/Y jogging.
  //-----------------------------------------------------------------------------
  this.jogXY_Stop = function()
  {
    winder.remoteAction( "process.jogXY( 0, 0 )" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start X/Y axis seek.
  //-----------------------------------------------------------------------------
  this.seekXY = function( x, y )
  {
    if ( null == x )
      x = $( "#seekX" ).val()

    if ( null == y )
      y = $( "#seekY" ).val()

    var velocity = maxVelocity
    var acceleration = maxAcceleration
    var deceleration = maxDeceleration
    winder.remoteAction
    (
      "process.manualSeekXY("
      + x + ","
      + y + ","
      + velocity + ","
      + acceleration + ","
      + deceleration + ")"
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Seek a point in machine geometry.
  // Input:
  //   x - Name of geometry variable that defines x position.
  //   y - Name of geometry variable that defines y position.
  //-----------------------------------------------------------------------------
  this.seekLocation = function( x, y )
  {
    var velocity = maxVelocity

    if ( x )
      x = "process.apa._gCodeHandler." + x
    else
      x = "None"

    if ( y )
      y = "process.apa._gCodeHandler." + y
    else
      y = "None"

    winder.remoteAction( "process.manualSeekXY( " + x + ", " + y + "," + velocity + ")"  )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start Z axis seek.
  //-----------------------------------------------------------------------------
  this.seekZ = function( position )
  {
    var z = position
    if ( null == z )
      z = $( "#seekZ" ).val()

    var velocity = maxVelocity
    winder.remoteAction( "process.manualSeekZ(" + z + "," + velocity + ")"  )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop Z axis jogging.
  //-----------------------------------------------------------------------------
  this.jogZ_Stop = function()
  {
    winder.remoteAction( "process.jogZ( 0 )" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start Z axis jogging.
  // Input:
  //   direction - Direction (1,-1, 0) of jog.
  //-----------------------------------------------------------------------------
  this.jogZ_Start = function( direction )
  {
    var velocity = maxVelocity * direction * speedLimit
    winder.remoteAction( "process.jogZ(" + velocity + ")"  )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully retract Z axis.
  //-----------------------------------------------------------------------------
  this.zRetract = function()
  {
    var velocity = maxVelocity
    winder.remoteAction( "process.manualSeekZ( 0, " + velocity + " )" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully extend Z axis.
  //-----------------------------------------------------------------------------
  this.zExtend = function()
  {
    var velocity = maxVelocity
    winder.remoteAction( "process.manualSeekZ( " + extendedPosition + ", " + velocity + " )" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Partly extend Z axis.
  //-----------------------------------------------------------------------------
  this.zMid = function()
  {
    var velocity = maxVelocity
    var position = extendedPosition / 2
    winder.remoteAction( "process.manualSeekZ( " + position + ", " + velocity + " )" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Run a latching operation.
  //-----------------------------------------------------------------------------
  this.latch = function()
  {
    winder.remoteAction( "io.plcLogic.latch()" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch homing sequence.
  //-----------------------------------------------------------------------------
  this.latchHome = function()
  {
    winder.remoteAction( "io.plcLogic.latchHome()" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch unlock.
  //-----------------------------------------------------------------------------
  this.latchUnlock = function()
  {
    winder.remoteAction( "io.plcLogic.latchUnlock()" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the position of the head.
  //-----------------------------------------------------------------------------
  this.headPosition = function( position )
  {
    var velocity = maxVelocity
    winder.remoteAction( "process.manualHeadPosition( " + position + "," + velocity + " )" )
  }

  //-----------------------------------------------------------------------------
  //-----------------------------------------------------------------------------
  this.seekPin = function()
  {
    var pin = $( "#seekPin" ).val().toUpperCase()
    var velocity = maxVelocity
    winder.remoteAction( "process.seekPin( '" + pin + "', " + velocity + " )" )
  }

  // Fetch fully extended position from machine calibration.
  winder.remoteAction
  (
    "machineCalibration.zBack",
    function( data )
    {
      extendedPosition = data
    }
  )




  // Maximum velocity.
  winder.remoteAction
  (
    'configuration.get( "maxAcceleration" )',
    function( data )
    {
      maxAcceleration = parseFloat( data )
    }
  )

  // Maximum velocity.
  winder.remoteAction
  (
    'configuration.get( "maxDeceleration" )',
    function( data )
    {
      maxDeceleration = parseFloat( data )
    }
  )

  // Maximum velocity.
  winder.remoteAction
  (
    'configuration.get( "maxVelocity" )',
    function( data )
    {
      maxVelocity = parseFloat( data )
    }
  )

  page.loadSubPage
  (
    "/Mobile/Modules/Position",
    "#position"
  )

  //
  // Bind the touch start/end events for each jog button.
  // (This cannot be done via HTML.)
  //

  $( "#jogXY_ul" )
    .bind( 'touchstart', function() { self.jogXY_Start( -1, +1 ) } )
    .bind( 'touchend', self.jogXY_Stop )

  $( "#jogXY_u" )
    .bind( 'touchstart', function() { self.jogXY_Start(  0, +1 ) } )
    .bind( 'touchend', self.jogXY_Stop )

  $( "#jogXY_ur" )
    .bind( 'touchstart', function() { self.jogXY_Start( +1, +1 ) } )
    .bind( 'touchend', self.jogXY_Stop )


  $( "#jogXY_l" )
    .bind( 'touchstart', function() { self.jogXY_Start( -1,  0 ) } )
    .bind( 'touchend', self.jogXY_Stop )

  $( "#jogXY_r" )
    .bind( 'touchstart', function() { self.jogXY_Start( +1,  0 ) } )
    .bind( 'touchend', self.jogXY_Stop )


  $( "#jogXY_dl" )
    .bind( 'touchstart', function() { self.jogXY_Start( -1, -1 ) } )
    .bind( 'touchend', self.jogXY_Stop )

  $( "#jogXY_d" )
    .bind( 'touchstart', function() { self.jogXY_Start(  0, -1 ) } )
    .bind( 'touchend', self.jogXY_Stop )

  $( "#jogXY_dr" )
    .bind( 'touchstart', function() { self.jogXY_Start( +1, -1 ) } )
    .bind( 'touchend', self.jogXY_Stop )


  $( "#jogZ_b" )
    .bind( 'touchstart', function() { self.jogZ_Start( -1 ) } )
    .bind( 'touchend', self.jogZ_Stop )

  $( "#jogZ_f" )
    .bind( 'touchstart', function() { self.jogZ_Start( +1 ) } )
    .bind( 'touchend', self.jogZ_Stop )

}
