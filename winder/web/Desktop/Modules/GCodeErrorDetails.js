///////////////////////////////////////////////////////////////////////////////
// Name: GCodeErrorDetails.js
// Uses: Body of the G-code error modal.  Rendered inside the shared Overlay.
///////////////////////////////////////////////////////////////////////////////

function GCodeErrorDetails( modules )
{
  var gCodeErrorWatch = modules.get( "GCodeErrorWatch" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Describe where the error happened from the error data array.
  // Input:
  //   data - Error data; conventionally [ lineNumber, lineText, ... ].
  // Output:
  //   Human-readable location string, empty when there is nothing useful.
  //-----------------------------------------------------------------------------
  var formatLocation = function( data )
  {
    if ( ! data || ! data.length )
      return ""

    // The wind path prefixes [ lineIndex, lineText ]; macros supply pin names.
    if ( ( data.length >= 2 ) && ( "number" == typeof data[ 0 ] ) )
      return "Line N" + ( data[ 0 ] + 2 ) + ": " + data[ 1 ]

    return data.join( ", " )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Paint the current error into the modal.
  //-----------------------------------------------------------------------------
  this.update = function()
  {
    var error = gCodeErrorWatch.currentError

    if ( ! error )
    {
      $( "#gCodeErrorMessage" ).text( "--" )
      $( "#gCodeErrorLocation" ).text( "" )
      return
    }

    $( "#gCodeErrorMessage" ).text( error.message )
    $( "#gCodeErrorLocation" ).text( formatLocation( error.data ) )
  }

  window[ "gCodeErrorDetails" ] = this
}
