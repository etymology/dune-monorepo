function Position( modules )
{
  var self = this
  var winder = modules.get( "Winder" )
  var commands = window.CommandCatalog

  // Public motor status data.
  this.motor = {}

  var readConfigValue = function( key )
  {
    winder.call
    (
      commands.configuration.get,
      { key: key },
      function( response )
      {
        if ( response && response.ok )
          self.motor[ key ] = parseFloat( response.data )
      }
    )
  }

  var readConfig = function()
  {
    readConfigValue( "maxAcceleration" )
    readConfigValue( "maxDeceleration" )
    readConfigValue( "maxVelocity" )
  }

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

  var updateAxis = function( axis, value )
  {
    self.motor[ axis + "Position" ] = value
    $( "#" + axis + "Position" ).text( formatFunction( value, 1 ) )
  }

  winder.addPeriodicCallback
  (
    commands.process.getUISnapshot,
    function( snapshot )
    {
      if ( snapshot && snapshot.axes )
      {
        updateAxis( "x", snapshot.axes.x.position )
        updateAxis( "y", snapshot.axes.y.position )
        updateAxis( "z", snapshot.axes.z.position )
      }
      else
      {
        updateAxis( "x", null )
        updateAxis( "y", null )
        updateAxis( "z", null )
      }
    }
  )

  readConfig()
  winder.addErrorClearCallback( readConfig )
}
