function Version( modules )
{
  var self = this

  this.softwareVersion =
  {
    "controlVersion" : 0,
    "uiVersion" : 0
  }

  var winder
  var commands = window.CommandCatalog

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback when version information box is clicked.
  //-----------------------------------------------------------------------------
  this.showVersionInformation = function()
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
          "/Desktop/Modules/VersionDetails",
          "#overlayBox",
          function()
          {
            var overlay = modules.get( "Overlay" )
            var versionDetails = modules.get( "VersionDetails" )
            overlay.show()
            versionDetails.versionUpdate()
          }
        )
      }
    )
  }

  this.loadVersion = function()
  {
    winder.singleRemoteDisplay
    (
      commands.version.getVersion,
      "#controlVersion",
      this.softwareVersion,
      "controlVersion"
    )

    winder.call
    (
      commands.version.verify,
      {},
      function( response )
      {
        var data = response && response.ok && response.data
        if ( data )
          $( "#controlVersion" ).attr( 'class', "" )
        else
          $( "#controlVersion" ).attr( 'class', "badVersion"  )
      }
    )

    winder.singleRemoteDisplay
    (
      commands.uiVersion.getVersion,
      "#uiVersion",
      this.softwareVersion,
      "uiVersion"
    )

    winder.call
    (
      commands.uiVersion.verify,
      {},
      function( response )
      {
        var data = response && response.ok && response.data
        if ( data )
          $( "#uiVersion" ).attr( 'class', "" )
        else
          $( "#uiVersion" ).attr( 'class', "badVersion" )
      }
    )
  }

  modules.load
  (
    [ "/Scripts/Winder" ],
    function()
    {
      winder = modules.get( "Winder" )
      self.loadVersion()
    }
  )

  window[ "version" ] = this
}
