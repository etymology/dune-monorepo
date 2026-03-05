
//=============================================================================
// Deal with serializeable configuration values.  These must come from a class
// that has a get, put, and save function.
//=============================================================================
function ConfigurationList( winder, remotePrefix, tagPrefix )
{
  var self = this
  var commands = window.CommandCatalog

  // Used to track the number of items still updating.  When all updates have
  // taken place, the data is saved.
  var triggers = 0
  var values = {}

  if ( null == tagPrefix )
    tagPrefix = remotePrefix

  var isConfiguration = ( "configuration" == remotePrefix )
  var isMachineCalibration = ( "machineCalibration" == remotePrefix )

  var executeGet = function( item, callback )
  {
    if ( isConfiguration )
    {
      winder.call
      (
        commands.configuration.get,
        { key: item },
        function( response )
        {
          if ( response && response.ok )
            callback( response.data )
        }
      )
      return
    }

    if ( isMachineCalibration )
    {
      winder.call
      (
        commands.machine.getCalibration,
        {},
        function( response )
        {
          if ( response && response.ok && response.data )
            callback( response.data[ item ] )
        }
      )
    }
  }

  var executeSet = function( item, value, callback )
  {
    if ( isConfiguration )
    {
      winder.call
      (
        commands.configuration.set,
        { key: item, value: value },
        function( response )
        {
          if ( callback )
            callback( response && response.ok )
        }
      )
      return
    }

    if ( isMachineCalibration )
    {
      winder.call
      (
        commands.machine.setCalibration,
        { key: item, value: value },
        function( response )
        {
          if ( callback )
            callback( response && response.ok )
        }
      )
    }
  }

  var executeSave = function()
  {
    if ( isConfiguration )
      winder.call( commands.configuration.save, {} )
    else
    if ( isMachineCalibration )
      winder.call( commands.machine.saveCalibration, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Save the modified values.
  //-----------------------------------------------------------------------------
  this.save = function()
  {
    executeSave()
    $( "#" + tagPrefix + "Save" ).prop( "disabled", true )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Submit all the changed values.
  //-----------------------------------------------------------------------------
  this.submitAll = function()
  {
    $( "#" + tagPrefix + " .changed" ).each
      (
        function()
        {
          triggers += 1
          $( this ).trigger( "submit" )
        }
      )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Revert all modified values to last saved values.
  //-----------------------------------------------------------------------------
  this.revert = function()
  {
    $( "#" + tagPrefix + " input" ).each
      (
        function()
        {
          var id = $( this ).attr( "id" ).replace( remotePrefix + ".", "" )
          $( this )
            .val( values[ id ] )
            .attr( "class", "" )

        }
      )

    $( "#" + tagPrefix + "Save" ).prop( "disabled", true )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Buttons to save and revert values.
  // Input:
  //   tag - Tag to which buttons are to be added.
  //-----------------------------------------------------------------------------
  this.buttonSet = function( tag )
  {
    var div = $( "<div />" ).appendTo( tag )

    $( "<button />" )
      .appendTo( div )
      .attr( 'id', tagPrefix + "Save" )
      .text( "Save" )
      .prop( "disabled", true )
      .click( self.submitAll )

    $( "<button />" )
      .appendTo( div )
      .attr( 'id', tagPrefix + "Revert" )
      .text( "Revert" )
      .click( self.revert )
  }

  //---------------------------------------------------------------------------
  // Uses:
  //   Load an I/O query into a table.
  // Input:
  //   listQuery - Query to run to get a list of I/O.
  //   itemQuery - Query to run to get status of a specific I/O point.
  //   tag - Tag to place I/O list after loading.
  //---------------------------------------------------------------------------
  this.display = function( name, item, tag, verifyFunction )
  {
    // If no verify function is specified, assume it should be numeric.
    if ( null == verifyFunction )
      verifyFunction = $.isNumeric

    var div = $( "<div />" ).appendTo( tag )
    var id = remotePrefix + "." + item
    executeGet
    (
      item,
      function( data )
      {
        values[ item ] = data

        // Text label for the item.
        $( "<label/>" )
          .attr( "for", id )
          .text( name )
          .appendTo( div )

        // Input to modify the item.
        $( "<input/>" )
          .val( data )
          .attr( "id", id )
          .on
          (
            "submit",
            // The submit function will actually set the value for this configuration
            // variable.  If it is the last submit called, it will also save
            // the configuration.
            function()
            {
              var changedObject = this
              var newValue = $( this ).val()

              // Submit new data.
              executeSet
              (
                item,
                newValue,
                function( isOk )
                {
                  if ( ! isOk )
                    return

                  // Initial value (for revert purposes) is now the new value.
                  values[ item ] = newValue

                  // Input is no longer being changed.
                  $( changedObject ).attr( "class", "" )

                  // If this is the last input to have been changed in the sequence,
                  // save the new values.
                  triggers -= 1
                  if ( 0 == triggers )
                    self.save()
                }
              )

            }
          )
          // Callback anytime the input changes.
          .on
          (
            "input",
            function()
            {
              var value = $( this ).val()
              // Different from initial value?
              if ( value != values[ item ] )
              {
                // Make sure this is a number
                if ( verifyFunction( value ) )
                  // The change function will only denote that a change has taken
                  // place--it will not commit this change.
                  $( this ).attr( "class", "changed" )
                else
                  $( this ).attr( "class", "error" )
              }
              else
                $( this ).attr( "class", "" )

              // Set the save button enable/disable based on any whether or not
              // there are are any modified input fields.
              var disabled = ( 0 == $( '.changed' ).length )
              $( "#" + tagPrefix + "Save" ).prop( "disabled", disabled )
            }
          )
          .appendTo( div )
      }
    )
  }
}

//=============================================================================
// Master class for screen.
//=============================================================================
function Configuration( modules )
{
  var self = this

  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )
  var commands = window.CommandCatalog

  var machineCalibration
  var configuration

  winder.addToggleButton
  (
    "#loggingButton",
    commands.process.getPositionLogging,
    function( value )
    {
      return {
        name: commands.process.setPositionLogging,
        args: { enabled: !! parseInt( value, 10 ) }
      }
    }
  )


  //---------------------------------------------------------------------------
  // Uses:
  //   Check for valid IP address in format "nnn.nnn.nnn.nnn".
  // Returns:
  //   True if valid, false if not.
  //---------------------------------------------------------------------------
  this.isIP_Address = function( ipAddress )
  {
    var testExpression = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
    return ( null != ipAddress.match( testExpression ) )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load all I/O.
  //-----------------------------------------------------------------------------
  this.loadConfiguration = function ()
  {

    // All parameters of machine calibration.
    var tag = $( "#machineCalibration" )
    tag.empty()
    machineCalibration = new ConfigurationList( winder, "machineCalibration" )
    machineCalibration.display( "Park x",             "parkX",            tag )
    machineCalibration.display( "Park y",             "parkY",            tag )
    machineCalibration.display( "Spool load x",       "spoolLoadX",       tag )
    machineCalibration.display( "Spool load y",       "spoolLoadY",       tag )
    machineCalibration.display( "Transfer left",      "transferLeft",     tag )
    machineCalibration.display( "Transfer left-top",  "transferLeftTop",  tag )
    machineCalibration.display( "Transfer top",       "transferTop",      tag )
    machineCalibration.display( "Transfer right",     "transferRight",    tag )
    machineCalibration.display( "Transfer right-top", "transferRightTop", tag )
    machineCalibration.display( "Transfer bottom",    "transferBottom",   tag )
    machineCalibration.display( "Limit left",         "limitLeft",        tag )
    machineCalibration.display( "Limit top",          "limitTop",         tag )
    machineCalibration.display( "Limit right",        "limitRight",       tag )
    machineCalibration.display( "Limit bottom",       "limitBottom",      tag )
    machineCalibration.display( "Retracted",          "zFront",           tag )
    machineCalibration.display( "Extended",           "zBack",            tag )
    machineCalibration.display( "Limit retracted",    "zLimitFront",      tag )
    machineCalibration.display( "Limit extended",     "zLimitRear",       tag )
    machineCalibration.display( "Arm length",         "headArmLength",    tag )
    machineCalibration.buttonSet( tag )

    // All parameters of machine setup.
    var tag = $( "#configuration" )
    tag.empty()
    configuration = new ConfigurationList( winder, "configuration" )
    configuration.display( "PLC address",        "plcAddress",       tag, self.isIP_Address )
    configuration.display( "Max velocity",       "maxVelocity",      tag )
    configuration.display( "Slow velocity",      "maxSlowVelocity",  tag )
    configuration.display( "Max acceleration",   "maxAcceleration",  tag )
    configuration.display( "Max deceleration",   "maxDeceleration",  tag )
    configuration.buttonSet( tag )
  }

  this.loadConfiguration()
  winder.addErrorClearCallback( this.loadConfiguration )

  // Motor status.
  page.loadSubPage
  (
    "/Desktop/Modules/MotorStatus",
    "#motorStatusDiv",
    function()
    {
      // Setup copy fields for motor positions.  Allows current motor positions
      // to be copied to input fields.
      var x = new CopyField( "#xPosition", "#xPositionCell" )
      var y = new CopyField( "#yPosition", "#yPositionCell" )
      var z = new CopyField( "#zPosition", "#zPositionCell" )
    }
  )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Used to create random APA entries.  Debug function.
  //   $$$TEMPORARY
  //-----------------------------------------------------------------------------
  this.createRandomAPA = function( number )
  {
    $( "#customCommandResult" ).val( "Legacy custom generators removed from API v2." )
  }

  winder.addEditField
  (
    "#velocity",
    "#velocityButton",
    commands.process.maxVelocity,
    function( value )
    {
      return {
        name: commands.process.maxVelocity,
        args: { value: value }
      }
    },
    $.isNumeric
  )

  winder.addEditField
  (
    "#acceleration",
    "#accelerationButton",
    commands.io.maxAcceleration,
    function( value )
    {
      return {
        name: commands.io.maxAcceleration,
        args: { value: value }
      }
    }
  )

  winder.addEditField
  (
    "#deceleration",
    "#decelerationButton",
    commands.io.maxDeceleration,
    function( value )
    {
      return {
        name: commands.io.maxDeceleration,
        args: { value: value }
      }
    }
  )

  $( "#customCommandButton" )
    .click
    (
      function()
      {
        var command = $( "#customCommand" ).val()
        command = $.trim( command )
        if ( ! command )
        {
          $( "#customCommandResult" ).val( "Enter a command name." )
          return
        }

        winder.call
        (
          command,
          {},
          function( response )
          {
            if ( response && response.ok )
              $( "#customCommandResult" ).val( JSON.stringify( response.data ) )
            else
            if ( response && response.error )
              $( "#customCommandResult" ).val( response.error.message )
            else
              $( "#customCommandResult" ).val( "Command failed." )
          }
        )
      }
    )

  // $$$TEMPORARY.
  this.logout = function()
  {
    winder.login
    (
      null,
      function( loginResult )
      {
        location.reload( true )
      }
    )
  }

  // $$$TEMPORARY.
  this.stop = function()
  {
    winder.shutdown()
  }

  window[ "configuration" ] = this
}
