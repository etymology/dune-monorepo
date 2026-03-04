///////////////////////////////////////////////////////////////////////////////
// Name: Page.js
// Uses: Page loading/switching with caching.
// Date: 2016-10-20
// Author(s):
//   Andrew Que <aque@bb7.com>
// Description:
//   A system for fast page switching.  Once pages are loaded, they can be
// switched quickly by loading them from cache.  A page consists of HTML, CSS,
// and Javascript modules.  When switching between pages, the HTML and CSS is
// saved and restored.  Javascript must be placed in modules that can shutdown
// and restore themselves.
///////////////////////////////////////////////////////////////////////////////

var Page = function()
{
  var FORCE_RELOAD = false

  // Reference to ourselves.
  var self = this

  // Instance of the page currently active.  Start with nothing.
  var activePage = null

  // Dictionary of all the pages loaded, indexed by page name.
  var loadedPages = {}

  // List of all modules loaded for every page.
  var commonModules = []

  // List of all sub-pages loaded on every page.
  var commonPages = []

  // Number of pages currently still loading.
  // Used for triggering fully-loaded event.
  var pagesLoading = 0

  // Callbacks run once pages is completely loaded.
  var onFullyLoadedCallbacks = []

  // Save all the loaded style sheet URLs.  These need to stay regardless
  // of what page is loaded.
  var baseStylesheets = []
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

  //----------------------------------------------------------------------------
  // Uses:
  //   Callback to run when a page is shutdown.  Passed to modules.
  // Input:
  //   page - Instance of Page to be shutdown.
  //----------------------------------------------------------------------------
  var pageShutdown = function( page )
  {
    // Save HTML of page.
    var mainDivName = page[ "tag" ]
    var tag = $( mainDivName ).html()
    page[ "html" ] = $( mainDivName ).html()

    // Erase main div and replace with loading message.
    $( mainDivName ).html( "Loading..." )

    // Remove all styles sheets that are not base styles and save their
    // links.
    page[ "css" ] = Array()
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
          {
            // Save link to CSS.
            page[ "css" ].push( url )

            // Remove it.
            $( this ).remove()
          }
        }
      )
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Callback to run when a page is restored.  Passed to modules.
  // Input:
  //   page - Instance of Page to be restored.
  //----------------------------------------------------------------------------
  var pageRestore = function( page )
  {
    // Restore HTML.
    $( page[ "tag" ] ).html( page[ "html" ] )

    // Restore all CSS.
    for ( var index in page[ "css" ] )
    {
      var css = page[ "css" ][ index ]
      var cssLink =
        $( "<link rel='stylesheet' type='text/css' href='" + css + "'>" )

      $( "head" ).append( cssLink )
    }

    // Restored page is now the active page.
    activePage = page
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Load a sub page into an HTML tag.
  // Input:
  //   pageName - Name of page to load.
  //   tag - HTML tag to place loaded content.
  //   callback - Callback to run when page has loaded.
  //   callbackParameters - Parameters to send to callback.
  // Output:
  //   Returns self to allow for command chaining.
  //----------------------------------------------------------------------------
  this.loadSubPage = function( pageName, tag, callback, callbackParameters )
  {
    // The random line is added to the end of a URL to force the browser to
    // actually load the data.  Otherwise, the browser may used a cached
    // version.
    var randomLine = ""
    if ( FORCE_RELOAD )
      randomLine = "?random=" + Math.random()

    var cssLink =
      $( "<link rel='stylesheet' type='text/css' href='" + pageName + ".css" + randomLine + "'>" )

    $( "head" ).append( cssLink )

    // Denote an other page is loading.
    pagesLoading += 1

    $( tag )
      .load
      (
        pageName + ".html" + randomLine,
        function()
        {
          activePage[ "modules" ].load
          (
            pageName,
            function()
            {
              // If there is a callback once page is finished loading, run it.
              if ( callback )
                callback( callbackParameters )

              // One more page is finished loading.
              pagesLoading -= 1

              // If all pages have been loaded, run fully loaded callbacks.
              if ( 0 == pagesLoading )
                for ( var index in onFullyLoadedCallbacks )
                  onFullyLoadedCallbacks[ index ]()
            }
          )
        }
      )

    return this
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Load a page either from server or restore from cache.
  // Input:
  //   page - Desired page to load.
  //   tag - HTML tag to place loaded content.
  //   callback - Callback to run when page has loaded.
  //   callbackParameters - Parameters to send to callback.
  //   failureCallback - Callback to run if page fails to load.
  // Output:
  //   Returns self to allow for command chaining.
  //----------------------------------------------------------------------------
  this.load = function( pageName, tag, callback, callbackParameters, failureCallback )
  {
    // Only if the page is actually changing...
    if ( ( ! ( pageName in loadedPages ) )
      || ( activePage != loadedPages[ pageName ] ) )
    {
      // If there is a page already active, shut it down.
      if ( activePage )
        activePage[ "modules" ].shutdown()

      // Is this page already loaded?
      if ( pageName in loadedPages )
      {
        // Simply restore the loaded version.
        loadedPages[ pageName ][ "modules" ].restore()
      }
      else
      {
        // Setup new active page.
        activePage = {}
        loadedPages[ pageName ] = activePage

        // Create instance of modules for this page.
        activePage[ "modules" ] = new Modules()

        // Setup module callbacks.
        activePage[ "modules" ]
          .registerLoadFailureCallback( failureCallback )
          .registerShutdownCallback( pageShutdown, activePage )
          .registerRestoreCallback( pageRestore, activePage )
          .register( "Page", self )

        // Remember the tag loaded HTML is to be placed.
        activePage[ "tag" ] = tag

        // Load all common modules.
        activePage[ "modules" ].load
        (
          commonModules,
          function()
          {
            // Load common sub-pages.
            for ( var index in commonPages )
              self.loadSubPage( commonPages[ index ][ "page" ], commonPages[ index ][ "tag" ] )

            // Start loading the page.
            // NOTE: The loadSubPage function could be the first of several.
            self.loadSubPage
            (
              pageName,
              tag,
              callback,
              callbackParameters
            )
          }
        )

      }
    }

    return this
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Setup a button to load a page.
  // Input:
  //   buttonTag - A <button> element.
  //   targetTag - Location page is to be loaded.
  //   pageName - Page to load.
  //   preCallback - Callback to run before new page is run.
  //   preCallbackParameters - Parameters to passed to preCallback.
  // Output:
  //   Returns self to allow for command chaining.
  // Notes:
  //   If used 'preCallback' must return false for the button to be invoked.
  //   Any other value will result abort the load.
  //----------------------------------------------------------------------------
  this.setupButton = function( buttonTag, targetTag, pageName, preCallback, preCallbackParameters )
  {
    $( buttonTag )
      .click
      (
        function()
        {
          // Run the pre-callback.  Checks to see if the load should be skipped.
          isSkip = false
          if ( preCallback )
            isSkip = preCallback( preCallbackParameters )

          if ( ! isSkip )
            self.load( pageName, targetTag )
        }
      )

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Add a callback to be run after the entire pages has finished loading.
  // Input:
  //   callback - Function to run.
  // Output:
  //   Returns self to allow for command chaining.
  //---------------------------------------------------------------------------
  this.addFullyLoadedCallback = function( callback )
  {
    onFullyLoadedCallbacks.push( callback )

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Add a module common to every page.
  // Input:
  //   module - Module name to load.
  // Output:
  //   Returns self to allow for command chaining.
  //---------------------------------------------------------------------------
  this.addCommonModule = function( module )
  {
    commonModules.push( module )

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Add a page common to every page.
  // Input:
  //   page - Name of page name to load.
  // Output:
  //   Returns self to allow for command chaining.
  //---------------------------------------------------------------------------
  this.addCommonPage = function( page, tag )
  {
    commonPages.push( { page: page, tag: tag } )

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Add load a module.
  // Input:
  //   module - Module name to load.
  //   callback - Function to run after everything has loaded.
  //   failCallback - Function to run if there is a problem loading module.
  // Output:
  //   Returns self to allow for command chaining.
  //---------------------------------------------------------------------------
  this.loadModule = function( module, callback, failCallback )
  {
    activePage[ "modules" ].load( module, callback, failCallback )

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get modules for active page.
  // Returns:
  //   Instance of Modules.
  //---------------------------------------------------------------------------
  this.getModules = function()
  {
    return activePage[ "modules" ]
  }
}
