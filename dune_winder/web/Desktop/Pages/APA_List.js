function APA_List( modules )
{
  var self = this

  var winder = modules.get( "Winder" )

  var STAGES =
  [
    "Uninitialized",
    "X first",
    "X second",
    "V first",
    "V second",
    "U first",
    "U second",
    "G first",
    "G second",
    "Sign off",
    "Complete",
  ]

  //-----------------------------------------------------------------------------
  // Uses:
  //   Convert a UTC time string from server to local time.
  // Input:
  //   UTC date/time string in "YYYY-MM-DD HH:MM:SS.UUUUUU" format.
  // Output:
  //   String in "YYYY-MM-DD HH:MM:SS AP" format adjusted for local time.
  //-----------------------------------------------------------------------------
  this.toLocalTime = function( timestamp )
  {
    // Time stamp needs to be in "yyyy-mm-ddThh:mm:ss.uuuuuuZ" format.
    timestamp = timestamp.replace( " ", "T" ) // <- Add T between date and time.
    timestamp += "Z"                          // <- For Zulu time.
    var date = new Date( timestamp )

    // Convert to 12 hours AM/PM.
    var hours = date.getHours()
    var ampm = "AM"
    if ( hours > 12 )
    {
      hours -= 12
      ampm = "PM"
    }
    else
    if ( 0 == hours )
      hours = 12

    // String together result.
    // The slice code zero pads the numbers.
    result =
      date.getFullYear()
      + "-"
      + ( "0" + date.getMonth() ).slice( -2 )
      + "-"
      + ( "0" + date.getDate() ).slice( -2 )
      + " "
      + ( "0" + hours ).slice( -2 )
      + ":"
      + ( "0" + date.getMinutes() ).slice( -2 )
      + ":"
      + ( "0" + date.getSeconds() ).slice( -2 )
      + " "
      + ampm

    return result
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Display the details of an APA.
  // Input:
  //   name - Name of APA to display.
  //-----------------------------------------------------------------------------
  this.loadDetails = function( name )
  {
    winder.remoteAction
    (
      'process.getAPA_Details( "' + name + '" )',
      function( data )
      {
        $( "#apaDetails_name"            ).text( data[ "_name"            ] )
        $( "#apaDetails_calibrationFile" ).text( data[ "_calibrationFile" ] )
        $( "#apaDetails_recipeFile"      ).text( data[ "_recipeFile"      ] )
        $( "#apaDetails_lineNumber"      ).text( data[ "_lineNumber"      ] )
        $( "#apaDetails_layer"           ).text( data[ "_layer"           ] )
        $( "#apaDetails_stage"           ).text( STAGES[ data[ "_stage" ] ] )
        $( "#apaDetails_creationDate"    ).text( self.toLocalTime( data[ "_creationDate"    ] ) )
        $( "#apaDetails_lastModifyDate"  ).text( self.toLocalTime( data[ "_lastModifyDate"  ] ) )
        $( "#apaDetails_loadedTime"      ).text( data[ "_loadedTime"      ] )
        $( "#apaDetails_windTime"        ).text( data[ "_windTime"        ] )
        $( "#apaDetails" ).slideDown()
      }
    )
  }

  var apaDetails = {}

  //-----------------------------------------------------------------------------
  // Uses:
  //   Display the details of an APA.
  // Input:
  //   name - Name of APA to display.
  //-----------------------------------------------------------------------------
  this.showDetails = function( name )
  {
    var data = apaDetails[ name ]

    $( "#apaDetails_name"            ).text( data[ "_name"            ] )
    $( "#apaDetails_calibrationFile" ).text( data[ "_calibrationFile" ] )
    $( "#apaDetails_recipeFile"      ).text( data[ "_recipeFile"      ] )
    $( "#apaDetails_lineNumber"      ).text( data[ "_lineNumber"      ] )
    $( "#apaDetails_layer"           ).text( data[ "_layer"           ] )
    $( "#apaDetails_stage"           ).text( STAGES[ data[ "_stage" ] ] )
    $( "#apaDetails_creationDate"    ).text( self.toLocalTime( data[ "_creationDate"    ] ) )
    $( "#apaDetails_lastModifyDate"  ).text( self.toLocalTime( data[ "_lastModifyDate"  ] ) )
    $( "#apaDetails_loadedTime"      ).text( data[ "_loadedTime"      ] )
    $( "#apaDetails_windTime"        ).text( data[ "_windTime"        ] )
    $( "#apaDetails" ).slideDown()
  }


  //-----------------------------------------------------------------------------
  // Uses:
  //   Load the log data into a filtered table.
  // Input:
  //   loadAll - True if all log data should be loaded, false to only load some.
  //-----------------------------------------------------------------------------
  this.loadData = function()
  {
    // Filter table object with columns for the log file.
    var apaListTable =
        new FilteredTable
        (
          [ "Name", "Creation", "Last Modified", "Hours", "Stage" ],
          [ false, false, false, false, true ],
          [ "20%", "20%", "20%", "20%", "20%" ]
        )

    winder.remoteAction
    (
      "process.getAPA_DetailedList()",
      function( data )
      {
        apaDetails = {}
        var apaList = []

        // Create a data set used by table from detailed information.
        for ( item of data )
        {
          var subSet = []
          subSet.push( item[ '_name' ] )
          subSet.push( self.toLocalTime( item[ '_creationDate' ] ) )
          subSet.push( self.toLocalTime( item[ '_lastModifyDate' ] ) )
          subSet.push( Math.round( item[ '_windTime' ] / 3600.0 * 100 ) / 100 )
          subSet.push( STAGES[ item[ '_stage' ] ] )

          apaList.push( subSet )

          // Add item to global list.
          // This dictionary, keyed by the APA name, will be used to display
          // the full details.
          apaDetails[ item[ '_name' ] ] = item
        }

        apaListTable.loadFromArray( apaList )
        apaListTable.setSort( "0", 1 )

        // For every row of the table, setup a click callback such that when
        // a row is clicked, it loads and displays the details of that entry.
        // This callback needs to be run any time the table is displayed.
        apaListTable.setDisplayCallback
        (
          function()
          {
            // For each row in table...
            $( "#apaList tr" )
              .each
              (
                function()
                {
                  // Get the name of the APA in this row.
                  // This is the text in the first cell of the row.
                  var localName = $( this ).find( "td" ).first().text()

                  // Add a click callback function.
                  $( this )
                    .click
                    (
                      function()
                      {
                        // Display the details about this name.
                        self.showDetails( localName )
                      }
                    )
                }
              )
          }
        )

        apaListTable.display( "#apaList" )

      }
    )
  }

  this.loadData()
}
//
// //-----------------------------------------------------------------------------
// // Uses:
// //   Called when page loads.
// //-----------------------------------------------------------------------------
// $( document ).ready
// (
//   function()
//   {
//     apaList = new APA_List()
//   }
// )

