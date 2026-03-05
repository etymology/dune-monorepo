function G_CodePage( modules )
{
  var self = this
  var winder = modules.get( "Winder" )
  var page = modules.get( "Page" )
  var commands = window.CommandCatalog
  var call = function( commandName, args, callback )
  {
    winder.call
    (
      commandName,
      args,
      function( response )
      {
        if ( response && response.ok )
        {
          if ( callback )
            callback( response.data, null )
        }
        else
        {
          if ( callback )
            callback( null, response )
        }
      }
    )
  }

  var G_CODE_ROWS = 2

  var gCodeLine = {}

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start G-Code execution.
  //-----------------------------------------------------------------------------
  this.start = function()
  {
    call( commands.process.start, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to immediately stop G-Code execution.
  //-----------------------------------------------------------------------------
  this.stop = function()
  {
    call( commands.process.stop, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to stop G-Code execution after completing current motion.
  //-----------------------------------------------------------------------------
  this.stopNext = function()
  {
    call( commands.process.stopNextLine, {} )
    $( "#stopNextButton" ).prop( "disabled", true )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to start G-Code execution of next line only.
  //-----------------------------------------------------------------------------
  this.step = function()
  {
    call( commands.process.step, {} )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to execute manual G-Code.
  //-----------------------------------------------------------------------------
  this.executeGCode = function()
  {
    $( "#gExecutionCodeStatus" ).html( "Request G-Code execution..." )

    var gCode = $( "#manualGCode" ).val()
    call
    (
      commands.process.executeGCodeLine,
      { line: gCode },
      function( data, error )
      {
        if ( error )
          $( "#gExecutionCodeStatus" ).html( "Error interpreting line: " + error.error.message )
        else
        if ( ! data )
          $( "#gExecutionCodeStatus" ).html( "Executed with no errors." )
        else
          $( "#gExecutionCodeStatus" ).html( "Error interpreting line: " + data )
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to advance G-Code by one line.
  //-----------------------------------------------------------------------------
  this.nextLine = function()
  {
    if ( null != gCodeLine[ "currentLine" ] )
    {
      // Next line is the current line because the current line has been incremented
      // by 1.
      var nextLine = gCodeLine[ "currentLine" ]
      if ( nextLine < ( gCodeLine[ "totalLines" ] - 1 ) )
        call( commands.process.setGCodeLine, { line: nextLine } )
    }
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Callback to retard G-Code by one line.
  //-----------------------------------------------------------------------------
  this.previousLine = function()
  {
    if ( null != gCodeLine[ "currentLine" ] )
    {
      var nextLine = gCodeLine[ "currentLine" ] - 2
      if ( nextLine >= -1 )
        call( commands.process.setGCodeLine, { line: nextLine } )
    }
  }

  page.loadSubPage
  (
    "/Mobile/Modules/Position",
    "#position"
  )

  page.loadSubPage
  (
    "/Mobile/Modules/G_Code",
    "#gCodeDiv",
    function()
    {
      var gCode = modules.get( "G_Code" )
      gCode.create( G_CODE_ROWS )
    }
  )

  // Set updates of current line and total lines.
  winder.addPeriodicCallback
  (
    commands.process.getGCodeLine,
    function( data )
    {
      if ( null !== data )
      {
        data = data + 1
        gCodeLine[ "currentLine" ] = data
      }
      else
      {
        data = "-"
        gCodeLine[ "currentLine" ] = null
      }

      $( "#currentLine" ).text( data )
    }
  )

  winder.addPeriodicRead
  (
    commands.process.getGCodeTotalLines,
    gCodeLine,
    "totalLines"
  )

  // Update for primary state machine.
  winder.addPeriodicCallback
  (
    commands.process.getControlStateName,
    // NOTE: Callback only runs when data has changed.
    function( state )
    {
      var isRunning = ( "StopMode" != state )

      $( "#startButton"    ).prop( "disabled", isRunning )
      $( "#stopButton"     ).prop( "disabled", ! isRunning )
      $( "#stopNextButton" ).prop( "disabled", ! isRunning )
      $( "#stepButton"     ).prop( "disabled", isRunning )
    }
  )

  window[ "gCodePage" ] = this
}
