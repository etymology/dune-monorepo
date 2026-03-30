function Version( modules )
{
  var self = this

  this.softwareVersion =
  {
    "controlVersion" : 0,
    "uiVersion" : 0
  }

  var uiServices = modules.get( "UiServices" )
  var commands = uiServices.getCommands()

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
    uiServices.call
    (
      commands.version.getVersion,
      {},
      function( data )
      {
        if ( data !== null )
        {
          self.softwareVersion[ "controlVersion" ] = data
          $( "#controlVersion" ).text( data )
        }
      }
    )

    uiServices.call
    (
      commands.version.verify,
      {},
      function( data )
      {
        if ( data )
          $( "#controlVersion" ).attr( 'class', "" )
        else
          $( "#controlVersion" ).attr( 'class', "badVersion" )
      }
    )

    uiServices.call
    (
      commands.uiVersion.getVersion,
      {},
      function( data )
      {
        if ( data !== null )
        {
          self.softwareVersion[ "uiVersion" ] = data
          $( "#uiVersion" ).text( data )
        }
      }
    )

    uiServices.call
    (
      commands.uiVersion.verify,
      {},
      function( data )
      {
        if ( data )
          $( "#uiVersion" ).attr( 'class', "" )
        else
          $( "#uiVersion" ).attr( 'class', "badVersion" )
      }
    )
  }

  self.loadVersion()
}
