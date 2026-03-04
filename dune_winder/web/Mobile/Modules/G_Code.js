function G_Code( modules )
{
  // Pointer to self.
  var self = this

  var winder = modules.get( "Winder" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Create G-Code table.  Call after loading.
  // Input:
  //   G_CODE_ROWS - Number of rows to display.
  //-----------------------------------------------------------------------------
  this.create = function( G_CODE_ROWS )
  {
    var totalRows = G_CODE_ROWS * 2 + 1
    $( "#gCodeTable" ).empty()
    var gGodeBody = $( "<tbody/>" ).appendTo( "#gCodeTable" )
    var gCodeMid = totalRows / 2
    for ( var rowIndex = 0; rowIndex < totalRows; rowIndex += 1 )
    {
      var newRow = $( "<tr/>" ).appendTo( gGodeBody )

      if ( G_CODE_ROWS == rowIndex )
        newRow.attr( "class", "gCodeCurrentLine" )
      else
      if ( G_CODE_ROWS - 1 == rowIndex )
        newRow.attr( "id", "gCodeReverseRow" )
      else
      if ( G_CODE_ROWS + 1 == rowIndex )
        newRow.attr( "id", "gCodeForwardRow" )

      var newCell = $( "<td/>" ).appendTo( newRow ).html( "&nbsp;" )
    }

    // Setup G-Code table.
    winder.addPeriodicCallback
    (
      "process.getG_CodeList( None, " + G_CODE_ROWS + " )",
      function( data )
      {
        // If there is any data.
        if ( data )
        {
          var index = 0
          // For each row of table...
          $( "#gCodeTable td" )
            .each
            (
              function()
              {
                var isForward = $( "#reverseButton" ).val()

                if ( ( "1" == isForward )
                  || ( null == isForward ) )
                {
                  $( "#gCodeForwardRow" ).attr( 'class', 'gCodeNextLine')
                  $( "#gCodeReverseRow" ).attr( 'class', '' )
                }
                else
                {
                  $( "#gCodeForwardRow" ).attr( 'class', '')
                  $( "#gCodeReverseRow" ).attr( 'class', 'gCodeNextLine' )
                }

                // Get text for this row.
                var text = data[ index ]

                // If there isn't any text, put in a non-breaking space to
                // preserve the cell.
                if ( ! text )
                  text = "&nbsp;"

                $( this ).html( text )
                index += 1
              }
            )
        }
      }
    )
  }

}
