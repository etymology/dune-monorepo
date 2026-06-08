///////////////////////////////////////////////////////////////////////////////
// Name: CopyField.js
// Uses: Copy text field to input value interface.
// Date: 2016-06-14
// Author(s):
//   Andrew Que <aque@bb7.com>
// Description:
//   Copy field is a dataTag that has a text field that can be copied to the value
// of an input dataTag by first clicking on the dataTag to be copied, and then on the
// input in which to copy it.
///////////////////////////////////////////////////////////////////////////////

//=============================================================================
// Input:
//   dataTag - Tag to allow to be copied.
//=============================================================================
function CopyField( dataTag, parentTag )
{
  // Local pointer to self.
  var self = this

  // Dictionary used to save original onclick callback functions.
  var originalClick = {}

  //---------------------------------------------------------------------------
  // Uses:
  //   Enable/disable copy field.
  // Input:
  //   isEnabled - True to enable.
  //---------------------------------------------------------------------------
  this.enableCopy = function( isEnabled )
  {

    $( ".copySelect" )
      .each
      (
        function()
        {
          $( this ).removeClass( "copySelect" )
        }
      )

    if ( isEnabled )
      $( parentTag ).addClass( "copySelect" )

    // Loop through all input fields...
    $( "input" )
      .each
      (
        function( index )
        {
          if ( isEnabled )
          {
            // Save the old handler.
            originalClick[ index ] = this.onclick

            // Set a new handler.
            // NOTE: We do not use jQuery's bind or click function because that
            // will add an event, not replace it.  We need to replace it.
            this.onclick =
              function()
              {
                var newValue = $( dataTag ).text()
                $( this )
                  .val( newValue )
                  .trigger( "input" )
                  .trigger( "change" )
                self.enableCopy( false )
              }

            $( this ).addClass( "copySelect" )
          }
          else
          {
            $( this ).removeClass( "copySelect" )

            // Restore original click function.
            this.onclick = originalClick[ index ]
          }
        }
      )
  }

  if ( null == parentTag )
    parentTag = dataTag

  // Setup copy field on requested dataTag.
  $( parentTag )
    .click
    (
      function()
      {
        var isEnabled = $( parentTag ).hasClass( "copySelect" )
        self.enableCopy( ! isEnabled )
      }
    )
}
