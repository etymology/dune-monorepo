function PLC_Status( modules )
{
  var winder = modules.get( "Winder" )
  var runStatus = modules.get( "RunStatus" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Reset button callback.
  //-----------------------------------------------------------------------------
  this.reset = function ()
  {
    winder.remoteAction( 'process.acknowledgeError()' )
  }
  
  // new function for PLC_Init - PWH - September 2021
  this.PLC_init = function ()
  {
    winder.remoteAction( 'process.acknowledgePLC_Init()' )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Close button callback.
  //-----------------------------------------------------------------------------
  this.close = function ()
  {
    var overlay = modules.get( "Overlay" )
    overlay.close()
  }

  // Start displaying PLC status.
  winder.addPeriodicEndCallback
  (
    function()
    {
      $( "#controlStateDetails" ).text( runStatus.states[ 'controlState' ] )
      $( "#plcStateDetails" ).text( runStatus.states[ 'plcState' ] )
      $( "#plcErrorDetails" ).text( runStatus.states[ 'plcError' ] )
    }
  )

  window[ "plcStatus" ] = this
}
