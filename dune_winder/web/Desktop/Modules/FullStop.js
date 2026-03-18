function FullStop( modules )
{
  var self = this

  var winder
  var commands = window.CommandCatalog

  modules.load
  (
    [ "/Scripts/Winder" ],
    function()
    {
      winder = modules.get( "Winder" )
    }
  )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for global stop button.
  //-----------------------------------------------------------------------------
  this.stop = function ()
  {
    winder.call( commands.process.stop, {} )
  }

  window[ "fullStop" ] = this
}
