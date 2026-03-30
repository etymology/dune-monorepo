function VersionDetails( modules )
{
  var uiServices = modules.get( "UiServices" )
  var commands = uiServices.getCommands()

  var display = function( commandName, selector )
  {
    uiServices.call
    (
      commandName,
      {},
      function( data )
      {
        if ( data !== null )
          $( selector ).text( data )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to update all the version information.
  //-----------------------------------------------------------------------------
  this.versionUpdate = function()
  {
    display( commands.version.getVersion, "#controlVersionString" )
    display( commands.version.getHash, "#controlVersionHash" )
    display( commands.version.getDate, "#controlVersionDate" )
    display( commands.version.verify, "#controlVersionValid" )

    display( commands.uiVersion.getVersion, "#uiVersionString" )
    display( commands.uiVersion.getHash, "#uiVersionHash" )
    display( commands.uiVersion.getDate, "#uiVersionDate" )
    display( commands.uiVersion.verify, "#uiVersionValid" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for recompute the user interface version button.
  //-----------------------------------------------------------------------------
  this.versionUI_Recompute = function()
  {
    uiServices.call
    (
      commands.uiVersion.update,
      {},
      function()
      {
        this.versionUpdate()
      }.bind( this )
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for recompute the control interface version button.
  //-----------------------------------------------------------------------------
  this.versionControlRecompute = function()
  {
    uiServices.call
    (
      commands.version.update,
      {},
      function()
      {
        this.versionUpdate()
      }.bind( this )
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Close overlay.
  //-----------------------------------------------------------------------------
  this.close = function ()
  {
    var version = modules.get( "Version" )
    version.loadVersion()

    var overlay = modules.get( "Overlay" )
    overlay.close()
  }

  window[ "versionDetails" ] = this
}
