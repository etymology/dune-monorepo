///////////////////////////////////////////////////////////////////////////////
// Name: UiServices.js
// Uses: Shared typed command access layer for page/modules.
///////////////////////////////////////////////////////////////////////////////

var UiServices = function( modules )
{
  var cachedWinder = null
  var commands = window.CommandCatalog || {}

  var getWinder = function()
  {
    if ( ! cachedWinder )
      cachedWinder = modules.get( "Winder" )

    return cachedWinder
  }

  // Expose command catalog from one shared location.
  this.commands = commands

  this.getCommands = function()
  {
    return commands
  }

  // Execute a typed command and split success/error handling.
  this.call = function( commandName, args, onSuccess, onError )
  {
    var winder = getWinder()
    if ( ! winder )
    {
      if ( onError )
      {
        onError
        (
          {
            ok: false,
            data: null,
            error:
            {
              code: "CLIENT_ERROR",
              message: "Winder module is unavailable."
            }
          }
        )
      }
      return
    }

    winder.call
    (
      commandName,
      args || {},
      function( response )
      {
        if ( response && response.ok )
        {
          if ( onSuccess )
            onSuccess( response.data, response )
        }
        else
        if ( onError )
          onError( response )
      }
    )
  }

  // Normalize and execute request objects with {name,args}.
  this.callRequest = function( request, onSuccess, onError )
  {
    if ( ! request || "object" != typeof request || "string" != typeof request.name )
    {
      if ( onError )
      {
        onError
        (
          {
            ok: false,
            data: null,
            error:
            {
              code: "BAD_REQUEST",
              message: "Request must include a command name."
            }
          }
        )
      }
      return
    }

    this.call( request.name, request.args || {}, onSuccess, onError )
  }
}
