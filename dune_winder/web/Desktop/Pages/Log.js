function Log( modules )
{
  var winder = modules.get( "Winder" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load the log data into a filtered table.
  // Input:
  //   loadAll - True if all log data should be loaded, false to only load some.
  //-----------------------------------------------------------------------------
  this.loadData = function( loadAll )
  {
    // Filter table object with columns for the log file.
    var filteredTable =
        new FilteredTable
        (
          [ "Time", "Module", "Type", "Description" ],
          [ false, true, true, false ],
          [ "200px", "150px", "150px" ]
        )

    var query = "log.getAll( 50 )"
    if ( loadAll )
      query = "log.getAll()"

    var loadingText = $( "<p />" )
      .attr( "id", "logTable" )
      .text( "Loading..." )

    $( "#logTable" ).replaceWith( loadingText )

    winder.remoteAction
    (
      query,
      function( data )
      {
        var dataSet = []

        for ( item of data )
        {
          var row = item.split( "\t" )

          // Get the time/date of occurrence and format it for local time.
          var time = new Date( row[ 0 ] + 'Z' )
          var timeString = $.format.date( time, "yyyy-MM-dd HH:mm:ss.SSS")
          row[ 0 ] = timeString

          dataSet.push( row )
        }

        filteredTable.loadFromArray( dataSet )
        filteredTable.setSort( 0, 1 )
        filteredTable.display( "#logTable" )

        $( "#logEntries" ).text( dataSet.length )
      }
    )
  }

  // Toggle button to select full-log or partial log display.
  winder.addToggleButton
  (
    "#fullLog",
    null,
    null,
    null,
    this.loadData
  )

  // Load initial data.
  this.loadData( false )

  window[ "log" ] = this
}

// //-----------------------------------------------------------------------------
// // Uses:
// //   Called when page loads.
// //-----------------------------------------------------------------------------
// $( document ).ready
// (
//   function()
//   {
//     log = new Log()
//   }
// )

