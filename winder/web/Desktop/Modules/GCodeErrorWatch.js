///////////////////////////////////////////////////////////////////////////////
// Name: GCodeErrorWatch.js
// Uses: Raise a modal popup when a G-code run faults.
// Notes:
//   A wind used to report G-code errors only as a row in the Recent Log table,
//   which is easy to miss while watching the machine.  This module polls the
//   latched backend error and puts it in front of the operator, and also
//   accepts errors pushed directly from a manual G-code line.
///////////////////////////////////////////////////////////////////////////////

function GCodeErrorWatch( modules )
{
  var self = this

  var winder = modules.get( "Winder" )
  var uiServices = modules.get( "UiServices" )
  var commands = uiServices.getCommands()

  // Payload the modal renders: { message: String, data: Array }.
  this.currentError = null

  // True between opening the modal and it being dismissed, so a repeated poll
  // result does not stack overlays.
  var isShowing = false

  //-----------------------------------------------------------------------------
  // Uses:
  //   Normalize the various error payload shapes into { message, data }.
  // Input:
  //   payload - A latched backend error, or an API error envelope's .error.
  // Output:
  //   Normalized object, or null when there is nothing to show.
  //-----------------------------------------------------------------------------
  var normalize = function( payload )
  {
    if ( ! payload )
      return null

    var message = payload.message
    if ( ! message )
      return null

    return { message: String( message ), data: payload.data || [] }
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Display an error in the shared Overlay modal.
  // Input:
  //   payload - Object with a "message" string and optional "data" array.
  //-----------------------------------------------------------------------------
  this.showError = function( payload )
  {
    var normalized = normalize( payload )
    if ( ! normalized )
      return

    self.currentError = normalized

    // Already open: just refresh the text in place.
    if ( isShowing )
    {
      var details = modules.get( "GCodeErrorDetails" )
      if ( details )
        details.update()

      return
    }

    isShowing = true

    var page = modules.get( "Page" )
    page.loadSubPage
    (
      "/Desktop/Modules/Overlay",
      "#modalDiv",
      function()
      {
        page.loadSubPage
        (
          "/Desktop/Modules/GCodeErrorDetails",
          "#overlayBox",
          function()
          {
            var overlay = modules.get( "Overlay" )
            var details = modules.get( "GCodeErrorDetails" )
            // Paint before the fade-in so the "--" placeholder is never seen.
            details.update()
            overlay.show()
          }
        )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Close the modal and tell the backend the error has been seen.
  //-----------------------------------------------------------------------------
  this.dismiss = function()
  {
    isShowing = false
    self.currentError = null

    uiServices.call( commands.process.acknowledgeGCodeError, {} )

    var overlay = modules.get( "Overlay" )
    if ( overlay )
      overlay.close()
  }

  // Watch for wind-time errors.  The periodic callback only fires when the
  // value changes, so this runs once when an error appears and once when it
  // is cleared.
  winder.addPeriodicCallback
  (
    commands.process.getGCodeError,
    function( data )
    {
      if ( data && data.message )
        self.showError( data )
    }
  )

  window[ "gCodeErrorWatch" ] = this
}
