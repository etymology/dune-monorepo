function VersionDetails( modules )
{
  var winder = modules.get( "Winder" )
  var commands = window.CommandCatalog

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to update all the version information.
  //-----------------------------------------------------------------------------
  this.versionUpdate = function()
  {
    winder.singleRemoteDisplay( commands.version.getVersion, "#controlVersionString" )
    winder.singleRemoteDisplay( commands.version.getHash, "#controlVersionHash" )
    winder.singleRemoteDisplay( commands.version.getDate, "#controlVersionDate" )
    winder.singleRemoteDisplay( commands.version.verify, "#controlVersionValid" )

    winder.singleRemoteDisplay( commands.uiVersion.getVersion, "#uiVersionString" )
    winder.singleRemoteDisplay( commands.uiVersion.getHash, "#uiVersionHash" )
    winder.singleRemoteDisplay( commands.uiVersion.getDate, "#uiVersionDate" )
    winder.singleRemoteDisplay( commands.uiVersion.verify, "#uiVersionValid" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for recompute the user interface version button.
  //-----------------------------------------------------------------------------
  this.versionUI_Recompute = function()
  {
    winder.call
    (
      commands.uiVersion.update,
      {},
      function( response )
      {
        if ( response && response.ok )
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
    winder.call
    (
      commands.version.update,
      {},
      function( response )
      {
        if ( response && response.ok )
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
