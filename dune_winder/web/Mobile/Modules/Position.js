function Position( modules )
{
  var self = this

  var winder = modules.get( "Winder" )

  // Public motor status data.
  this.motor = {}

  //-----------------------------------------------------------------------------
  // Uses:
  //   Read configuration variables related to motor limits. (Private)
  //-----------------------------------------------------------------------------
  var readConfig = function()
  {
    winder.remoteAction
    (
      'configuration.get( "maxAcceleration" )',
      function( data )
      {
        self.motor[ "maxAcceleration" ] = parseFloat( data )
      }
    )

    winder.remoteAction
    (
      'configuration.get( "maxDeceleration" )',
      function( data )
      {
        self.motor[ "maxDeceleration" ] = parseFloat( data )
      }
    )

    winder.remoteAction
    (
      'configuration.get( "maxVelocity" )',
      function( data )
      {
        self.motor[ "maxVelocity" ] = parseFloat( data )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Format a number with request number of decimal places.  (Private)
  // Input:
  //   data - Number to format.
  //   decimals - Number of decimal places.
  // Output:
  //   Number rounded to the requested decimal places.
  //-----------------------------------------------------------------------------
  var formatFunction = function( data, decimals )
  {
    if ( $.isNumeric( data ) )
    {

      var multiplier = Math.pow( 10, decimals )
      data = Math.round( data * multiplier ) / multiplier
    }
    else
      data = "-"

    return data
  }

  readConfig()
  var AXIES = [ "x", "y", "z" ]
  for ( var index in AXIES )
  {
    var axis = AXIES[ index ]

    winder.addPeriodicDisplay
    (
      "io." + axis + "Axis.getPosition()",
      "#" + axis + "Position",
      this.motor,
      axis + "Position",
      formatFunction,
      1
    )

    winder.addPeriodicDisplay
    (
      "io." + axis + "Axis.getPosition()",
      "#" + axis + "Position",
      this.motor,
      axis + "Position",
      formatFunction,
      1
    )
  }
}
