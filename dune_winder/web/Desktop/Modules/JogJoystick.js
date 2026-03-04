function JogJoystick( modules )
{
  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )

  var motorStatus
  modules.load
  (
    "/Desktop/Modules/MotorStatus",
    function()
    {
      motorStatus = modules.get( "MotorStatus" )
    }
  )

  // Function to get velocity of jog.
  var getVelocity     = function() { return 0; }
  var getAcceleration = function() { return null; }
  var getDeceleration = function() { return null; }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the function to return motion limit parameters.
  // Input:
  //   velocity - Function that returns max velocity.
  //   acceleration - Function that returns max acceleration.
  //   deceleration - Function that returns max deceleration.
  //-----------------------------------------------------------------------------
  this.callbacks = function( velocity, acceleration, deceleration )
  {
    getVelocity     = velocity
    getAcceleration = acceleration
    getDeceleration = deceleration
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start X/Y axis jog.
  // Input:
  //   x - Direction (1,-1, 0) for x-axis.
  //   y - Direction (1,-1, 0) for y-axis.
  //-----------------------------------------------------------------------------
  this.start = function( x, y )
  {
    // Convert direction to velocity.
    var velocity = getVelocity()
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

    var acceleration = getAcceleration()
    var deceleration = getDeceleration()

    winder.remoteAction
    (
      "process.jogXY(" + x + "," + y + "," + acceleration + "," + deceleration + ")"
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop X/Y jogging.
  //-----------------------------------------------------------------------------
  this.stop = function()
  {
    winder.remoteAction( "process.jogXY( 0, 0 )" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start X/Y axis seek.
  //-----------------------------------------------------------------------------
  this.seekXY = function( x, y )
  {
    var velocity     = getVelocity()
    var acceleration = getAcceleration()
    var deceleration = getDeceleration()

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

  window[ "jogJoystick" ] = this
}