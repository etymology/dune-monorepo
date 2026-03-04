function Time( modules )
{
  var self = this

  modules.load
  (
    [ "/Scripts/Winder" ],
    function()
    {
      var winder = modules.get( "Winder" )

      // Display system time.
      winder.addPeriodicDisplay
      (
        "systemTime.get()",
        "#systemTime",
        null,
        null,
        function( data )
        {
          var timeString = "--"
          if ( data )
          {
            var time = new Date( data + 'Z' )
            timeString = $.format.date( time, "yyyy-MM-dd HH:mm:ss.SSS")
          }

          return timeString
        }
      )
    }
  )
}
