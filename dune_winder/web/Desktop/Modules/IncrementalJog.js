function IncrementalJog( modules )
{
  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )
  var commands = window.CommandCatalog

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
    var velocity = getVelocity()
    var x = motorStatus.motor[ "xPosition" ] + offset
    var y = motorStatus.motor[ "yPosition" ]

    winder.call
    (
      commands.process.manualSeekXY,
      { x: x, y: y, velocity: velocity }
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
    var velocity = getVelocity()
    var x = motorStatus.motor[ "xPosition" ]
    var y = motorStatus.motor[ "yPosition" ] + offset
    winder.call
    (
      commands.process.manualSeekXY,
      { x: x, y: y, velocity: velocity }
    )
  }

  window[ "incrementalJog" ] = this
}
