function VersionDetails( modules )
{
  var winder = modules.get( "Winder" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to update all the version information.
  //-----------------------------------------------------------------------------
  this.versionUpdate = function()
  {
    winder.singleRemoteDisplay( "version.getVersion()", "#controlVersionString" )
    winder.singleRemoteDisplay( "version.getHash()", "#controlVersionHash" )
    winder.singleRemoteDisplay( "version.getDate()", "#controlVersionDate" )
    winder.singleRemoteDisplay( "version.verify()", "#controlVersionValid" )

    winder.singleRemoteDisplay( "uiVersion.getVersion()", "#uiVersionString" )
    winder.singleRemoteDisplay( "uiVersion.getHash()", "#uiVersionHash" )
    winder.singleRemoteDisplay( "uiVersion.getDate()", "#uiVersionDate" )
    winder.singleRemoteDisplay( "uiVersion.verify()", "#uiVersionValid" )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for recompute the user interface version button.
  //-----------------------------------------------------------------------------
  this.versionUI_Recompute = function()
  {
    winder.remoteAction( "uiVersion.update()", this.versionUpdate )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback for recompute the control interface version button.
  //-----------------------------------------------------------------------------
  this.versionControlRecompute = function()
  {
    winder.remoteAction( "version.update()", this.versionUpdate )
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
