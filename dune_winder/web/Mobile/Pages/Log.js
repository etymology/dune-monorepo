function Log( modules )
{
  var self = this
  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )

  var LOG_ENTIRES = 8

  // Status of state machines.
  var states =
  {
    "controlState" : 0,
    "plcState" : 0
  }

  // Update for primary state machine.
  winder.addPeriodicDisplay
  (
    "process.controlStateMachine.state.__class__.__name__",
    "#controlState",
    states,
    "controlState"
  )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Acknowledge errors button callback.
  //-----------------------------------------------------------------------------
  this.acknowledgeErrors = function()
  {
    winder.remoteAction( 'process.acknowledgeError()' )
  }

  // Update for PLC state machine.
  winder.addPeriodicCallback
  (
    "io.plcLogic.getState()",
    function( value )
    {
      if ( null !== value )
      {
        var stateTranslateTable =
        [
          "Init",          // 0
          "Ready",         // 1
          "XY jog",        // 2
          "XY seek",       // 3
          "Z jog",         // 4
          "Z seek",        // 5
          "Latching",      // 6
          "Latch homing",  // 7
          "Latch release", // 8
          "Unservo",       // 9
          "Error"          // 10
        ]

        var stringValue = stateTranslateTable[ value ]
        states[ "plcState" ] = stringValue
        $( "#plcState" ).text( stringValue )

        // Change the CSS class for a PLC state error.
        if ( 10 == value )
          $( "#plcState" ).attr( 'class', 'plcError' )
        else
          $( "#plcState" ).attr( 'class', '' )

      }
      else
        $( "#plcState" ).html( winder.errorString )
    }
  )

  page.loadSubPage
  (
    "/Desktop/Modules/RecentLog",
    "#recentLogDiv",
    function()
    {
      var recentLog = modules.get( "RecentLog" )
      recentLog.create( LOG_ENTIRES )
    }
  )

  window[ "log" ] = this
}
