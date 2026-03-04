function RunStatus( modules )
{
  var self = this

  this.states = {}

  //-----------------------------------------------------------------------------
  // Uses:
  //   See if machine is running based on control state.
  // Output:
  //   True if running, false if not.
  //-----------------------------------------------------------------------------
  this.isRunning = function()
  {
    var state = self.states[ "controlState" ]
    var result = ( "StopMode" != state ) && ( "HardwareMode" != state )
    return result
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   See if the machine is currently in motion.
  // Output:
  //   True if in motion, false if not.
  //-----------------------------------------------------------------------------
  this.isInMotion = function()
  {
    var controlState = self.states[ "controlState" ]
    var plcState = self.states[ "plcState" ]
    var inMotion =
         ( "StopMode" != controlState )
      && ( "HardwareMode" != controlState )
      && ( "Unservo" != plcState )

    return inMotion
  }


  //-----------------------------------------------------------------------------
  // Uses:
  //   Show the PLC status details pop-up.
  //-----------------------------------------------------------------------------
  this.showDetails = function()
  {
    var page = modules.get( "Page" )
    page.loadSubPage
    (
      "/Desktop/Modules/Overlay",
      "#modalDiv",
      function()
      {
        page.loadSubPage
        (
          "/Desktop/Modules/PLC_Status",
          "#overlayBox",
          function()
          {
            var overlay = modules.get( "Overlay" )
            var plcStatus = modules.get( "PLC_Status" )
            overlay.show()
            plcStatus.update()
          }
        )
      }
    )
  }

  //-----------------------------------------------------------------------------
  modules.load
  (
    [ "/Scripts/Winder" ],
    function()
    {
      var winder = modules.get( "Winder" )

      winder.addPeriodicRead
      (
        "io.plcLogic.getErrorCodeString()",
        self.states,
        "plcError"
      )

      // Update for primary state machine.
      winder.addPeriodicDisplay
      (
        "process.controlStateMachine.state.__class__.__name__",
        "#controlState",
        self.states,
        "controlState"
      )

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
            self.states[ "plcState" ] = stringValue
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

      winder.addPeriodicEndCallback
      (
        function()
        {
          $( "#controlState" ).text( self.states[ "controlState" ] )
        }
      )

    }
  )

  window[ "runStatus" ] = this
}
