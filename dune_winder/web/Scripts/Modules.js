///////////////////////////////////////////////////////////////////////////////
// Name: Modules.js
// Uses: Loadable modules interface.
// Date: 2016-10-20
// Author(s):
//   Andrew Que <aque@bb7.com>
// Description:
//   A module is a Javascript class contained in a file of the same name.
//   By loading it, a single instance of the module is created which can be
//   used by other modules.
///////////////////////////////////////////////////////////////////////////////

var Modules = function()
{
  // Reference to ourselves.
  var self = this

  // Dictionary of loaded modules.  Indexed by module name and contains the
  // instance of the module.
  var modules = {}

  // List of all modules loaded or loading.
  var loadedModules = []

  // Number of modules currently loading.
  // Used to track when all modules have completed loading.
  var modulesLoading = 0

  // List of callbacks to run when all modules have finished loading.
  // Modules may request other modules, so no callback is run until all load
  // requests have finished.
  var loadingCallbacks = []

  // List of callbacks to run in the event a module fails to load.
  var loadFailureCallbacks = []

  // List of callbacks and parameters to run when the module is shutdown.
  var shutdownCallbacks = []
  var shutdownCallbackParameters = {}

  // List of callbacks and parameters to run when the module is restored.
  var restoreCallbacks = []
  var restoreCallbackParameters = {}

  //---------------------------------------------------------------------------
  // Uses:
  //   Add a callback that is to run if there is a failure to load a module.
  //   Multiple callbacks can be registered.
  // Input:
  //   callback - Function to run should module fail to load.
  // Output:
  //   Returns self to allow for command chaining.
  //---------------------------------------------------------------------------
  this.registerLoadFailureCallback = function( callback )
  {
    if ( callback )
      loadFailureCallbacks.push( callback )

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Manually register a module already loaded.
  // Input:
  //   module - Module name to load.
  //   instance - An instance of this module.
  //---------------------------------------------------------------------------
  this.register = function( module, instance )
  {
    // Add to list of loaded modules.
    loadedModules.push( module )

    // Add to list of module instances.
    modules[ module ] = instance
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
  this.load = function( module, callback, failCallback )
  {
    // This function run all the callbacks if all modules have loaded.
    var checkCallbacks = function()
    {
      if ( 0 == modulesLoading )
      {
        var callbacksToRun = loadingCallbacks
        loadingCallbacks = []
        for ( var index in callbacksToRun )
        {
          var callbackSet = callbacksToRun[ index ]
          callbackSet[ 0 ]( callbackSet[ 1 ] )
        }
      }
    }

    // Function to run should there be a problem loading the module.
    var errorFunction = function()
    {
      if ( failCallback )
        failCallback( module )

      // Run all load failure callbacks.
      for ( var index in loadFailureCallbacks )
        loadFailureCallbacks[ index ]( module )
    }

    if ( Array.isArray( module ) )
    {
      for ( var index in module )
      {
        this.load( module[ index ], callback )

        // We only want the callback to run once, and they all run once
        // everything is loaded.  So null the callback for remainder of modules.
        callback = null
      }
    }
    else
    // If module is already loaded (or loading)...
    if ( -1 != loadedModules.indexOf( module ) )
    {
      // If there is a callback, add it to the callback list and check callbacks.
      if ( callback )
      {
        loadingCallbacks.unshift( [ callback, modules[ module ] ] )
        checkCallbacks()
      }
    }
    else
    {
      // An other module is now loading.
      modulesLoading += 1

      // Add module to list of those loaded.
      // NOTE: This is done before the module is finish loading so a second
      // request for the module doesn't result in a second load.
      loadedModules.push( module )

      // Request the module.
      $.getScript( module + ".js" )
        // When requested module has been loaded...
        .done
        (
          function()
          {
            // Try and create an instance of the module.
            try
            {
              // Create instance of this module.
              // NOTE: Loaded modules exist in global name space.
              var moduleName = module.replace( /(.*\/)?(.+)$/g, "$2" )
              modules[ moduleName ] = new window[ moduleName ]( self )

              // If there is a callback, add it to list of callbacks to run once
              // all modules have been loaded.
              if ( callback )
                loadingCallbacks.unshift( [ callback, modules[ module ] ] )
            }
            catch ( exception )
            {
              console.log( "Failed to create instance of " + module )

              // Any exception means the module failed to load correctly.
              errorFunction()
            }

            // Module count is one closer to finished.
            modulesLoading -= 1

            // Check to see if all modules have been loaded.
            checkCallbacks()
          }
        )
        // If unable to load requested module...
        .fail
        (
          function()
          {
            errorFunction()

            // Module count is one closer to finished.
            modulesLoading -= 1

            console.log( "Failed to load " + module )

            // Check to see if all modules have been loaded.
            checkCallbacks()
          }
        )
    }

    return this
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Get instance of a module.
  // Input:
  //   module - Module name to load.
  // Output:
  //   Instance of this module.  Null if the module isn't loaded.
  //---------------------------------------------------------------------------
  this.get = function( module )
  {
    return modules[ module ]
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Add a callback to list of functions called when the module is shutdown.
  // Input:
  //   callback - Function to run.
  //   callbackParameter - Parameters to sent to callback function.
  // Output:
  //   Returns self to allow for command chaining.
  //----------------------------------------------------------------------------
  this.registerShutdownCallback = function( callback, callbackParameters )
  {
    shutdownCallbacks.push( callback )
    shutdownCallbackParameters[ callback ] = callbackParameters

    return this
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Add a callback to list of functions called when the module is restored.
  // Input:
  //   callback - Function to run.
  //   callbackParameter - Parameters to sent to callback function.
  // Output:
  //   Returns self to allow for command chaining.
  //----------------------------------------------------------------------------
  this.registerRestoreCallback = function( callback, callbackParameters )
  {
    restoreCallbacks.push( callback )
    restoreCallbackParameters[ callback ] = callbackParameters

    return this
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Restore this module after having been shutdown.
  // Output:
  //   Returns self to allow for command chaining.
  //----------------------------------------------------------------------------
  this.restore = function()
  {
    for ( var index in restoreCallbacks )
    {
      var callback = restoreCallbacks[ index ]
      callback( restoreCallbackParameters[ callback ] )
    }

    return this
  }

  //----------------------------------------------------------------------------
  // Uses:
  //   Shutdown module.
  // Output:
  //   Returns self to allow for command chaining.
  //----------------------------------------------------------------------------
  this.shutdown = function()
  {
    // Shutdown modules in reverse order from how they were loaded...
    for ( var index in shutdownCallbacks.reverse() )
    {
      var callback = shutdownCallbacks[ index ]
      callback( shutdownCallbackParameters[ callback ] )
    }

    return this
  }
}
