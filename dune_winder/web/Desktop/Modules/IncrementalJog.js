function IncrementalJog( modules )
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
    var y = "None"

    winder.remoteAction( "process.manualSeekXY( " + x + ", " + y + "," + velocity + ")"  )
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
    var x = "None"
    var y = motorStatus.motor[ "yPosition" ] + offset
    winder.remoteAction( "process.manualSeekXY( " + x + ", " + y + "," + velocity + ")"  )
  }

  window[ "incrementalJog" ] = this
}