function FullStop( modules )
{
  var self = this

  var winder

  modules.load
  (
    [ "/Scripts/Winder", "/Desktop/Modules/RunStatus" ],
    function()
    {
      winder = modules.get( "Winder" )
      var runStatus = modules.get( "RunStatus" )

      // Button enable.
      winder.addPeriodicEndCallback
      (
        function()
        {
          var isDisabled = ! runStatus.isInMotion()
          $( "#fullStopButton" ).prop( "disabled", isDisabled )
        }
      )
    }
  )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for global stop button.
  //-----------------------------------------------------------------------------
  this.stop = function ()
  {
    winder.remoteAction( 'process.stop()' )
  }

  window[ "fullStop" ] = this
}
