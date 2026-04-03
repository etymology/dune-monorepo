function IncrementalJog( modules )
{
  var uiServices = modules.get( "UiServices" )
  var page = modules.get( "Page" )
  var commands = uiServices.getCommands()

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
  var getVelocity

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the function that will return maximum velocity.
  // Input:
  //   callback - Function that returns velocity.
  //-----------------------------------------------------------------------------
  this.velocityCallback = function( callback )
  {
    getVelocity = callback
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Make an incremental move in X.
  // Input:
  //   offset - Value (+/-) to move.
  //-----------------------------------------------------------------------------
  this.moveX = function( offset )
  {
    if ( ! motorStatus || ! motorStatus.motor )
      return

    var velocity = getVelocity()
    var rawX = motorStatus.motor[ "xPosition" ]
    var y = motorStatus.motor[ "yPosition" ]
    var requestMove = function( realX )
    {
      var x = parseFloat( realX )
      if ( isNaN( x ) )
        x = rawX

      uiServices.call
      (
        commands.process.manualSeekXY,
        { x: x + offset, y: y, velocity: velocity }
      )
    }

    if ( ! commands.process.getRealXPosition )
    {
      requestMove( rawX )
      return
    }

    uiServices.call
    (
      commands.process.getRealXPosition,
      {},
      function( realX )
      {
        requestMove( realX )
      },
      function()
      {
        requestMove( rawX )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Make an incremental move in Y.
  // Input:
  //   offset - Value (+/-) to move.
  //-----------------------------------------------------------------------------
  this.moveY = function( offset )
  {
    if ( ! motorStatus || ! motorStatus.motor )
      return

    var velocity = getVelocity()
    var y = motorStatus.motor[ "yPosition" ] + offset
    uiServices.call
    (
      commands.process.manualSeekXY,
      { y: y, velocity: velocity }
    )
  }

  window[ "incrementalJog" ] = this
}
