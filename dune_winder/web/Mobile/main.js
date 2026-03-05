var USE_FULL_PAGE_CACHE = false
var APP_STATE =
{
  page: null,
  baseStylesheets: []
}

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
function setupMainScreen( page )
{
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
        )
    }
  )
}

var PAGE_NAME_MAP =
{
  apa: "APA",
  log: "Log",
  io: "IO",
  calibrate: "Calibrate",
  vtemplate: "VTemplate",
  configuration: "Configuration",
  manualmovepopup: "ManualMovePopup"
}

function sanitizePageName( pageName )
{
  if ( ! pageName )
    return "APA"

  var key = ( "" + pageName ).replace( /\s+/g, "" ).toLowerCase()
  if ( key in PAGE_NAME_MAP )
    return PAGE_NAME_MAP[ key ]

  return "APA"
}

function removeNonBaseStylesheets()
{
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
        if ( -1 == APP_STATE.baseStylesheets.indexOf( url ) )
          // Remove it.
          $( this ).remove()
      }
    )
}

function configureCommonModules( page )
{
  // Winder module is used on every page.
  page.addCommonModule( "/Scripts/Winder" )
  page.addCommonModule( "/Scripts/UiServices" )

  // Keep desktop behavior for controls and runtime state.
  page.addCommonPage( "/Desktop/Modules/RunStatus", "#statesDiv" )
  page.addCommonPage( "/Desktop/Modules/FullStop", "#fullStopDiv" )
}

function createPageController()
{
  var page = new Page()
  APP_STATE.page = page
  configureCommonModules( page )
  return page
}

function load( pageName )
{
  var page = APP_STATE.page
  var sanitizedPageName = sanitizePageName( pageName )

  if ( ! USE_FULL_PAGE_CACHE )
  {
    if ( page )
    {
      var modules = page.getModules()
      modules.shutdown()
    }

    $( '#main' ).html( "Loading..." )

    removeNonBaseStylesheets()

    page = createPageController()
  }

  // Loading sub page and setup main screen after sub page finishes loading.
  if ( page )
    page.load
    (
      "/Desktop/Pages/" + sanitizedPageName,
      "#main",
      function()
      {
        setupMainScreen( page )
      },
      null,
      function( error )
      {
        alert( "Error loading page. " + error )
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
    // Save all loaded style sheets.  These stay regardless of page changes.
    APP_STATE.baseStylesheets = []
    $( 'head' )
      .find( 'link' )
      .each
      (
        function()
        {
          APP_STATE.baseStylesheets.push( $( this ).attr( 'href' ) )
        }
      )

    // Mobile intentionally launches into the Wind/APA interface.
    load( "APA" )
  }
)
