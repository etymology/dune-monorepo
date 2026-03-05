function RecentLog( modules )
{
  // Pointer to self.
  var self = this

  var winder = modules.get( "Winder" )
  var commands = window.CommandCatalog

  function formatDescription( row )
  {
    var description = row[ 3 ]
    var debugData = row.slice( 4 ).filter( function( item ) { return item !== "" } )
    if ( debugData.length > 0 )
      description += " [" + debugData.join( ", " ) + "]"

    return description
  }

  this.create = function( LOG_ENTIRES )
  {
    var table = $( "<table />" ).appendTo( "#recentLog" )
    var row = $( "<tr />" ).appendTo( table )
    $( "<th />" ).appendTo( row ).text( "Time" )
    $( "<th />" ).appendTo( row ).text( "Description" )
    for ( var index = 0; index < LOG_ENTIRES; index += 1 )
    {
      var row = $( "<tr />" ).appendTo( table )
      $( "<td />" )
        .appendTo( row )
        .attr( "id", "logTable" + index + "Time" )
        .text( "-" )

      $( "<td />" )
        .appendTo( row )
        .attr( "id", "logTable" + index + "Description" )
        .text( "-" )
    }

    winder.addPeriodicCallback
    (
      commands.log.getRecent,
      function( data )
      {
        for ( var index = 0; index < LOG_ENTIRES; index += 1 )
        {
          var dataIndex = -1

          var description = "-"
          var timeString = "-"

          if ( data )
          {
            dataIndex = data.length - index - 1

            if ( dataIndex >= 0 )
            {
              var row = data[ data.length - index - 1 ].split( "\t" )

              // Get the time/date of occurrence and format it for local time.
              var time = new Date( row[ 0 ] + 'Z' )
              timeString = $.format.date( time, "yyyy-MM-dd HH:mm:ss.SSS")

              description = formatDescription( row )
            }
          }

          $( "#logTable" + index + "Time" ).text( timeString )
          $( "#logTable" + index + "Description" ).text( description )
        }
      }
    )
  }
}

//var recentLog = new RecentLog()
