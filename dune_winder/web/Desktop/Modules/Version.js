function Version( modules )
{
  var self = this

  this.softwareVersion =
  {
    "controlVersion" : 0,
    "uiVersion" : 0
  }

  var winder

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
      "version.getVersion()",
      "#controlVersion",
      this.softwareVersion,
      "controlVersion"
    )

    winder.remoteAction
    (
      "version.isValid()",
      function( data )
      {
        if ( data )
          $( "#controlVersion" ).attr( 'class', "" )
        else
          $( "#controlVersion" ).attr( 'class', "badVersion"  )
      }
    )

    winder.singleRemoteDisplay
    (
      "uiVersion.getVersion()",
      "#uiVersion",
      this.softwareVersion,
      "uiVersion"
    )

    winder.remoteAction
    (
      "uiVersion.isValid()",
      function( data )
      {
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
