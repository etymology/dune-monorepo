function Increment( modules )
{
  var self = this

  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )
  var position
  var commands = window.CommandCatalog

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to seek to specified pin.
  //-----------------------------------------------------------------------------
  this.seekPin = function()
  {
    var pin = $( "#seekPin" ).val().toUpperCase()
    var velocity = position.motor[ "maxVelocity" ]
    winder.call
    (
      commands.process.seekPin,
      { pin: pin, velocity: velocity }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Make an incremental move in X.
  // Input:
  //   offset - Value (+/-) to move.
  //-----------------------------------------------------------------------------
  this.moveX = function( offset )
  {
    var velocity = position.motor[ "maxVelocity" ]
    var x = position.motor[ "xPosition" ] + offset
    var y = position.motor[ "yPosition" ]
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
    var velocity = position.motor[ "maxVelocity" ]
    var x = position.motor[ "xPosition" ]
    var y = position.motor[ "yPosition" ] + offset
    winder.call
    (
      commands.process.manualSeekXY,
      { x: x, y: y, velocity: velocity }
    )
  }

  page.loadSubPage
  (
    "/Mobile/Modules/Position",
    "#position",
    function()
    {
      position = modules.get( "Position" )
    }
  )

  window[ "increment" ] = this
}
