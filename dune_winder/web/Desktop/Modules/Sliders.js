function Sliders( modules )
{
  var MIN_VELOCITY = 1.0
  var MIN_ACCELERATION = 1.0

  var self = this
  var winder = modules.get( "Winder" )

  var sliderValues =
  {
   "velocitySlider"     : 100,
   "accelerationSlider" : 100,
   "decelerationSlider" : 100
  }

  var isLoaded =
  {
    velocitySlider     : false,
    accelerationSlider : false,
    decelerationSlider : false
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Get the desired velocity.
  //-----------------------------------------------------------------------------
  this.getVelocity = function()
  {
    return document.getElementById( "velocitySlider" ).scaledValue()
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Get the desired positive acceleration.
  //-----------------------------------------------------------------------------
  this.getAcceleration = function()
  {
    return document.getElementById( "accelerationSlider" ).scaledValue()
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Get the desired negative acceleration.
  //-----------------------------------------------------------------------------
  this.getDeceleration = function()
  {
    return document.getElementById( "decelerationSlider" ).scaledValue()
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set a slider to specified value.
  // Input:
  //   value - New value of slider (0-100).
  //-----------------------------------------------------------------------------
  function setSlider( slider, value )
  {
    // The slider may not yet be initialized.  For such cases, the create
    // function is latched to set the value.
    if ( isLoaded[ slider ] )
      $( "#" + slider ).slider( "value", value )
    else
      $( "#" + slider )
        .on
        (
          "slidecreate",
          function()
          {
            $( "#" + slider ).slider( "value", value )
          }
        )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the velocity slider.
  // Input:
  //   value - New value of slider.
  //-----------------------------------------------------------------------------
  this.setVelocity = function( value )
  {
    setSlider( "velocitySlider", value )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the acceleration slider.
  // Input:
  //   value - New value of slider.
  //-----------------------------------------------------------------------------
  this.setAcceleration = function( value )
  {
    setSlider( "accelerationSlider", value )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Set the deceleration slider.
  // Input:
  //   value - New value of slider.
  //-----------------------------------------------------------------------------
  this.setDeceleration= function( value )
  {
    setSlider( "decelerationSlider", value )
  }

  //-----------------------------------------------------------------------------
  // Uses
  //   Construct a slider.
  // Input:
  //   query - Query to fetch maximum value.
  //   sliderTag - HTML tag to place slider.
  //   valueTag - HTML tag to print value of slider.
  //   valueUnits - Text units to display after value.
  //   minimum - Smallest allowed value.
  // Notes:
  //   All sliders run from 0-100 internally.
  //-----------------------------------------------------------------------------
  function createSlider( query, sliderTag, valueTag, valueUnits, minimum )
  {
    // Maximum value query.
    winder.remoteAction
    (
      query,
      function( data )
      {
        var maximum = parseFloat( data )

        // Callback when slider is changed.
        sliderFunction =
          function( event, ui )
          {
            sliderValues[ sliderTag ] = ui.value
            var value = ui.value / 100.0 * ( maximum - minimum ) + minimum
            value = Math.round( value * 10.0 ) / 10.0
            $( "#" + valueTag ).html( value + " " + valueUnits )
          }

        ui = new function() { this.value = sliderValues[ sliderTag ] }
        sliderFunction( null, ui )

        // Function to get the scaled value of slider.
        document.getElementById( sliderTag ).scaledValue =
          function()
          {
            // Start with the level of the velocity slider.
            var value = parseFloat( $( this ).slider( "value" )  )

            // Correctly scale the velocity.
            value /= 100.0
            value *= ( maximum - minimum )
            value += minimum

            return value
          }

        $( "#" + sliderTag )
          .slider
          (
            {
              min: 0,
              max: 100,
              value: sliderValues[ sliderTag ],
              change: sliderFunction,
              slide: sliderFunction,
              create:
                function()
                {
                  velocitySlider[ sliderTag ] = true
                }
            }
          )

      }
    )

  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Construct each of the three sliders.  Call on start-up and when
  //   communication is reestablished.
  //-----------------------------------------------------------------------------
  function createSliders()
  {
    createSlider
    (
      'process.maxVelocity()',
      "velocitySlider",
      "velocityValue",
      "mm/s",
      MIN_VELOCITY
    )

    createSlider
    (
      'io.plcLogic.maxAcceleration()',
      "accelerationSlider",
      "accelerationValue",
      "mm/s<sup>2</sup>",
      MIN_ACCELERATION
    )

    createSlider
    (
      'io.plcLogic.maxDeceleration()',
      "decelerationSlider",
      "decelerationValue",
      "mm/s<sup>2</sup>",
      MIN_ACCELERATION
    )

  }

  createSliders()
  winder.addErrorClearCallback( createSliders )
}