var USE_FULL_PAGE_CACHE = false

//-----------------------------------------------------------------------------
// Uses:
//   Get a parameter in the GET portion of the URL.
// Input:
//   name - Name of parameter to return.
//   url - Full URL.  If left blank the URL of the current page is used.
// Output:
//   Value of the named parameter.
// Notes:
//   Copied from StackOverflow.com.
//-----------------------------------------------------------------------------
function getParameterByName( name, url )
{
  if ( ! url )
    url = window.location.href

  name = name.replace( /[\[\]]/g, "\\$&" )
  var regex = new RegExp( "[?&]" + name + "(=([^&#]*)|&|#|$)" )
  var results = regex.exec( url )

  var returnResult
  if ( ! results )
    returnResult = null
  else
  if ( ! results[ 2 ] )
    returnResult = ''
  else
    returnResult = decodeURIComponent( results[ 2 ].replace( /\+/g, " " ) )

  return returnResult
}

//-----------------------------------------------------------------------------
// Uses:
//   Setup main screen.
//
// $$$FUTURE - Remove this function and merge it into cache callback.  Only
//   needed for old system.
//-----------------------------------------------------------------------------
function setupMainScreen()
{
  var page = window[ "page" ]

  // Before sub-pages begin to load, register a callback to run after all
  // have been loaded.
  page.addFullyLoadedCallback
  (
    function()
    {
      $( "main article" ).each
      (
        function()
        {
          //$( this ).draggable().resizable()
        }
      )

      $( "button.makeToggle" )
        .each
        (
          function()
          {
            if ( $( this ).val() )
              $( this ).attr( "class", "toggleDown" )
            else
              $( this ).attr( "class", "toggle" )

            //if ( ! $( this ).click() )
            {
              $( this )
                .click
                (
                  function()
                  {
                    $( this ).toggleClass( "toggle" )
                    $( this ).toggleClass( "toggleDown" )

                    var value = 0
                    if ( $( this ).attr( 'class' ) == "toggleDown" )
                      value = 1

                    $( this ).val( value )
                  }
                )
            }

          }
        )

    }
  )
}

//-----------------------------------------------------------------------------
// Uses:
//   Callback for loading an other page.
// Input:
//   page - Desired page to load.
//-----------------------------------------------------------------------------
var baseStylesheets = []

function isPopupMode()
{
  return "1" == getParameterByName( "popup" )
}

function load( pageName )
{
  var page = window[ "page" ]

  if ( ! USE_FULL_PAGE_CACHE )
  {
    var modules = page.getModules()
    modules.shutdown()

    $( '#main' ).html( "Loading..." )

    // Remove all styles sheets that are not base styles.
    $( 'head' )
      .find( 'link' )
      .each
      (
        function()
        {
          // Where did this style sheet come from?
          var url = $( this ).attr( 'href' )

          // Is it a base style sheet?
          if ( -1 == baseStylesheets.indexOf( url ) )
            // Remove it.
            $( this ).remove()
        }
      )

    var page = new Page()
    window[ "page" ] = page

    // Winder module is used on every page.
    page.addCommonModule( "/Scripts/Winder" )

    page.addCommonPage( "/Desktop/Modules/RunStatus",   "#statesDiv"   )
    page.addCommonPage( "/Desktop/Modules/Time",        "#timeDiv"     )
    page.addCommonPage( "/Desktop/Modules/Version",     "#versionDiv"  )
    page.addCommonPage( "/Desktop/Modules/FullStop",    "#fullStopDiv" )

    // Loading sub page and setup main screen after sub page finishes loading.
    page.load
    (
      pageName,
      "#main",
      setupMainScreen,
      null,
      function( module )
      {
        alert( "Problems loading the module: " + module )
      }
    )
  }
  else
    // Loading sub page and setup main screen after sub page finishes loading.
    page.load
    (
      pageName,
      "#main",
      setupMainScreen,
      null,
      function( module )
      {
        alert( "Problems loading the module: " + module )
      }
    )
}

//-----------------------------------------------------------------------------
// Uses:
//   Called when page loads.
//-----------------------------------------------------------------------------
$( document ).ready
(
  function()
  {
    // Get the requested page.
    var pageName = getParameterByName( "page" )
    var popupMode = isPopupMode()

    // If there is no page, use default.
    if ( ! pageName )
      pageName = "APA"

    // Save all the loaded style sheet URLs.  These need to stay regardless
    // of what page is loaded.
    $( 'head' )
      .find( 'link' )
      .each
      (
        function()
        {
          // Add to list of base style sheets.
          baseStylesheets.push( $( this ).attr( 'href' ) )
        }
      )

    var page = new Page()
    window[ "page" ] = page

    if ( popupMode )
      $( "body" ).addClass( "popupMode" )
    else
    {
      $( "#pageSelectDiv" ).css( "display", "block" )
      $( "#fullStopDiv" ).css( "display", "block" )
      $( "#loginDiv" ).css( "display", "none" )
    }

    // Winder module is used on every page.
    page.addCommonModule( "/Scripts/Winder" )

    if ( ! popupMode )
    {
      page.addCommonPage( "/Desktop/Modules/RunStatus",   "#statesDiv"   )
      page.addCommonPage( "/Desktop/Modules/Time",        "#timeDiv"     )
      page.addCommonPage( "/Desktop/Modules/Version",     "#versionDiv"  )
      page.addCommonPage( "/Desktop/Modules/FullStop",    "#fullStopDiv" )
    }

    // Load the requested page.
    page.load
    (
      "/Desktop/Pages/" + pageName,
      "#main",
      setupMainScreen,
      null,
      function( error )
      {
        alert( "Error loading page. " + error )
      }
    )

    // $$$FUTURE // Check authentication either load requested page, or show grid page.
    // $$$FUTURE winder = new WinderInterface()
    // $$$FUTURE winder.remoteAction
    // $$$FUTURE (
    // $$$FUTURE   'RemoteSession.isAuthenticated( "' + $.cookie( "sessionId" ) + '" )',
    // $$$FUTURE   function( status )
    // $$$FUTURE   {
    // $$$FUTURE     console.log( "isAuthenticated = " + status )
    // $$$FUTURE     if ( ! status )
    // $$$FUTURE     {
    // $$$FUTURE       load( "grid" )
    // $$$FUTURE       $( "#loginDiv" ).css( "display", "block" )
    // $$$FUTURE     }
    // $$$FUTURE     else
    // $$$FUTURE     {
    // $$$FUTURE       $( "#pageSelectDiv" ).css( "display", "block" )
    // $$$FUTURE       $( "#fullStopDiv" ).css( "display", "block" )
    // $$$FUTURE       $( "#loginDiv" ).css( "display", "none" )
    // $$$FUTURE
    // $$$FUTURE       // Load the requested page.
    // $$$FUTURE       page.load( page )
    // $$$FUTURE     }
    // $$$FUTURE   }
    // $$$FUTURE )
  }
)

// $$$FUTURE //-----------------------------------------------------------------------------
// $$$FUTURE // Uses:
// $$$FUTURE //   Callback when version information box is clicked.
// $$$FUTURE //-----------------------------------------------------------------------------
// $$$FUTURE function showLogin()
// $$$FUTURE {
// $$$FUTURE   winder.loadSubPage
// $$$FUTURE   (
// $$$FUTURE     "/Desktop/Modules/overlay",
// $$$FUTURE     "#modalDiv",
// $$$FUTURE     function()
// $$$FUTURE     {
// $$$FUTURE       winder.loadSubPage( "/Desktop/Modules/login", "#overlayBox" )
// $$$FUTURE     }
// $$$FUTURE   )
// $$$FUTURE }

