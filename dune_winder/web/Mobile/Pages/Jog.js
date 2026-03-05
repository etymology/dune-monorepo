function Jog( modules )
{
  var self = this

  var page = modules.get( "Page" )
  var uiServices = modules.get( "UiServices" )
  var commands = uiServices.getCommands()
  var call = function( commandName, args, callback )
  {
    uiServices.call
    (
      commandName,
      args,
      function( data )
      {
        if ( callback )
          callback( data, null )
      },
      function( response )
      {
        if ( callback )
          callback( null, response )
      }
    )
  }

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

    call
    (
      commands.process.jogXY,
      {
        x_velocity: x,
        y_velocity: y,
        acceleration: acceleration,
        deceleration: deceleration,
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop X/Y jogging.
  //-----------------------------------------------------------------------------
  this.jogXY_Stop = function()
  {
    call( commands.process.jogXY, { x_velocity: 0, y_velocity: 0 } )
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
    call
    (
      commands.process.manualSeekXY,
      {
        x: x,
        y: y,
        velocity: velocity,
        acceleration: acceleration,
        deceleration: deceleration,
      }
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
    call
    (
      commands.process.manualSeekXYNamed,
      {
        x_name: x || null,
        y_name: y || null,
        velocity: velocity,
      }
    )
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
    call( commands.process.manualSeekZ, { position: z, velocity: velocity } )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop Z axis jogging.
  //-----------------------------------------------------------------------------
  this.jogZ_Stop = function()
  {
    call( commands.process.jogZ, { velocity: 0 } )
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
    call( commands.process.jogZ, { velocity: velocity } )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully retract Z axis.
  //-----------------------------------------------------------------------------
  this.zRetract = function()
  {
    var velocity = maxVelocity
    call( commands.process.manualSeekZ, { position: 0, velocity: velocity } )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Fully extend Z axis.
  //-----------------------------------------------------------------------------
  this.zExtend = function()
  {
    var velocity = maxVelocity
    call(
      commands.process.manualSeekZ,
      { position: extendedPosition, velocity: velocity }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Partly extend Z axis.
  //-----------------------------------------------------------------------------
  this.zMid = function()
  {
    var velocity = maxVelocity
    var position = extendedPosition / 2
    call( commands.process.manualSeekZ, { position: position, velocity: velocity } )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Run a latching operation.
  //-----------------------------------------------------------------------------
  this.latch = function()
  {
    call( commands.io.latch, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch homing sequence.
  //-----------------------------------------------------------------------------
  this.latchHome = function()
  {
    call( commands.io.latchHome, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Switch to latch unlock.
  //-----------------------------------------------------------------------------
  this.latchUnlock = function()
  {
    call( commands.io.latchUnlock, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the position of the head.
  //-----------------------------------------------------------------------------
  this.headPosition = function( position )
  {
    var velocity = maxVelocity
    call(
      commands.process.manualHeadPosition,
      { position: position, velocity: velocity }
    )
  }

  //-----------------------------------------------------------------------------
  //-----------------------------------------------------------------------------
  this.seekPin = function()
  {
    var pin = $( "#seekPin" ).val().toUpperCase()
    var velocity = maxVelocity
    call( commands.process.seekPin, { pin: pin, velocity: velocity } )
  }

  // Fetch fully extended position from machine calibration.
  call
  (
    commands.machine.getZBack,
    {},
    function( data )
    {
      extendedPosition = data
    }
  )




  // Maximum velocity.
  call
  (
    commands.configuration.get,
    { key: "maxAcceleration" },
    function( data )
    {
      maxAcceleration = parseFloat( data )
    }
  )

  // Maximum velocity.
  call
  (
    commands.configuration.get,
    { key: "maxDeceleration" },
    function( data )
    {
      maxDeceleration = parseFloat( data )
    }
  )

  // Maximum velocity.
  call
  (
    commands.configuration.get,
    { key: "maxVelocity" },
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

  var bindControls = function()
  {
    $( "#jogXY_home" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.seekXY( 0, 0 ) } )

    $( "#jogZ_home" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.seekZ( 0 ) } )

    $( "#jogHeadFront" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.headPosition( 0 ) } )

    $( "#jogHeadBack" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.headPosition( 3 ) } )

    $( "#jogHeadLevelFront" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.headPosition( 1 ) } )

    $( "#jogHeadLevelBack" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.headPosition( 2 ) } )

    $( "#jogSpeed50" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.setSpeed( 0.5 ) } )

    $( "#jogSpeed20" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.setSpeed( 0.2 ) } )

    $( "#jogSpeed10" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.setSpeed( 0.1 ) } )

    $( "#jogSpeed1" )
      .off( "click.jog" )
      .on( "click.jog", function() { self.setSpeed( 0.01 ) } )
  }

  bindControls()
  modules.registerRestoreCallback( bindControls )

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
