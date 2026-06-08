function FullStop( modules )
{
  var self = this

  var uiServices = modules.get( "UiServices" )
  var commands = uiServices.getCommands()

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for global stop button.
  //-----------------------------------------------------------------------------
  this.stop = function ()
  {
    uiServices.call( commands.process.stop, {} )
  }

  window[ "fullStop" ] = this
}
