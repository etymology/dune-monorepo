function RecentLog( modules )
{
  // Pointer to self.
  var self = this

  var winder = modules.get( "Winder" )

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
      "log.getRecent()",
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

              description = row[ 3 ]
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
