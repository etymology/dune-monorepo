function Calibrate(modules)
{
  var page = modules.get( "Page" )
  var winder = modules.get( "Winder" )
  var motorStatus = null
  var fixedVelocity = 1000
  var lastState = null
  var suppressWireRefresh = false
  var suppressOffsetRefresh = false
  var boardRoutine =
  {
    active: false,
    currentPin: null
  }

  modules.load
  (
    "/Desktop/Modules/MotorStatus",
    function()
    {
      motorStatus = modules.get( "MotorStatus" )
    }
  )

  page.loadSubPage
  (
    "/Desktop/Modules/ManualMove",
    "#manualMoveCard",
    function()
    {
      var manualMove = modules.get( "ManualMove" )
      manualMove.configure
      (
        {
          context: "calibrate",
          velocityCallback: currentVelocity,
          enablePositionCopy: true
        }
      )
    }
  )

  function formatNumber( value, decimals )
  {
    if ( ! $.isNumeric( value ) )
      return "-"

    var multiplier = Math.pow( 10, decimals )
    value = Math.round( value * multiplier ) / multiplier
    return value.toFixed( decimals )
  }

  function formatPair( xValue, yValue )
  {
    return "X " + formatNumber( xValue, 3 ) + "  Y " + formatNumber( yValue, 3 )
  }

  function capitalize( text )
  {
    if ( ! text )
      return "-"

    return text.charAt( 0 ).toUpperCase() + text.slice( 1 )
  }

  function referenceLabel( referenceId )
  {
    if ( referenceId == "foot" )
      return "B1 (foot)"

    return "B960 (head)"
  }

  function isGXMode()
  {
    return !! lastState && lastState.mode == "gx"
  }

  function isUVMode()
  {
    return ! lastState || ! lastState.mode || lastState.mode == "uv"
  }

  function baselineLabel( source )
  {
    if ( source == "nominal" )
      return "Clean APA / nominal"

    if ( source == "live" )
      return "Recalibrate / live XML"

    if ( source == "loaded" )
      return "Current loaded calibration"

    return capitalize( source )
  }

  function setMessage( text, cssClass )
  {
    var tag = $( "#manualCalibrationMessage" )
    tag
      .removeClass( "error" )
      .removeClass( "success" )

    if ( cssClass )
      tag.addClass( cssClass )

    tag.text( text || "" )
  }

  function currentVelocity()
  {
    return fixedVelocity
  }

  function getSelectedPin()
  {
    var pin = parseInt( $( "#manualCalibrationPin" ).val(), 10 )
    if ( isNaN( pin ) )
      return null

    return pin
  }

  function getSelectedBoardPin()
  {
    var pin = parseInt( $( "#manualCalibrationBoardSelect" ).val(), 10 )
    if ( isNaN( pin ) )
      return null

    return pin
  }

  function getSelectedReferenceId()
  {
    var referenceId = $( "#manualCalibrationReferenceSelect" ).val()
    if ( referenceId == "foot" )
      return "foot"

    return "head"
  }

  function setSelectedPin( pin, forceFieldUpdate )
  {
    if ( ! $.isNumeric( pin ) )
      return

    $( "#manualCalibrationPin" ).val( pin )
    if ( getBoardCheckEntry( pin ) )
    {
      setSelectedBoardPin( pin )
      renderBoardSelectionDetails()
    }
    refreshPrediction( forceFieldUpdate )
  }

  function setSelectedBoardPin( pin )
  {
    if ( ! $.isNumeric( pin ) )
      return

    $( "#manualCalibrationBoardSelect" ).val( pin )
  }

  function getReferenceEntry( referenceId )
  {
    if ( ! lastState || ! lastState.references )
      return null

    return lastState.references[ referenceId ] || null
  }

  function setFieldValueIfIdle( selector, value, isSuppressed )
  {
    var tag = $( selector )
    if ( ! isSuppressed && document.activeElement !== tag.get( 0 ) )
      tag.val( value )
  }

  function statusTag( status )
  {
    return '<span class="manualCalibrationStatusTag '
      + status
      + '">'
      + capitalize( status )
      + "</span>"
  }

  function workflowButtons( pin )
  {
    return ""
      + '<button type="button" data-action="goto" data-pin="' + pin + '">Go</button>'
      + '<button type="button" data-action="ok" data-pin="' + pin + '">Mark OK</button>'
      + '<button type="button" data-action="capture" data-pin="' + pin + '">Capture</button>'
      + '<button type="button" data-action="edit" data-pin="' + pin + '">Edit</button>'
  }

  function getBoardCheckItems()
  {
    if ( ! lastState || ! lastState.boardChecks )
      return []

    return lastState.boardChecks
  }

  function getBoardCheckEntry( pin )
  {
    var items = getBoardCheckItems()
    for ( var index in items )
    {
      if ( items[ index ].pin == pin )
        return items[ index ]
    }

    return null
  }

  function getBoardCheckIndex( pin )
  {
    var items = getBoardCheckItems()
    for ( var index in items )
    {
      if ( items[ index ].pin == pin )
        return parseInt( index, 10 )
    }

    return -1
  }

  function nextPendingBoardPin( currentPin )
  {
    var items = getBoardCheckItems()
    if ( 0 == items.length )
      return null

    var startIndex = getBoardCheckIndex( currentPin )
    for ( var offset = 1; offset <= items.length; offset += 1 )
    {
      var item = items[ ( startIndex + offset + items.length ) % items.length ]
      if ( item.status == "pending" )
        return item.pin
    }

    return null
  }

  function nextOtherPendingBoardPin( currentPin )
  {
    var pin = nextPendingBoardPin( currentPin )
    if ( pin == currentPin )
      return null

    return pin
  }

  function renderBoardSelectionDetails()
  {
    var pin = getSelectedBoardPin()
    var entry = getBoardCheckEntry( pin )
    if ( ! entry )
    {
      $( "#manualCalibrationBoardSelectSummary" ).text( "No board endpoints available." )
      $( "#manualCalibrationBoardSelectTarget" ).text( "Select an end pin to sync it into the pin workspace." )
      return
    }

    $( "#manualCalibrationBoardSelectSummary" )
      .html(
        "B"
        + entry.pin
        + "  |  Board "
        + entry.boardIndex
        + "  |  "
        + capitalize( entry.side )
        + "  |  "
        + statusTag( entry.status )
      )
    $( "#manualCalibrationBoardSelectTarget" )
      .text(
        "Camera "
        + formatPair( entry.predictedCameraX, entry.predictedCameraY )
        + "  |  Wire "
        + formatPair( entry.predictedWireX, entry.predictedWireY )
      )
  }

  function renderBoardDropdown( items )
  {
    var select = $( "#manualCalibrationBoardSelect" )
    if ( ! items || 0 == items.length )
    {
      select.html( '<option value="">No board endpoints</option>' )
      select.prop( "disabled", true )
      renderBoardSelectionDetails()
      return
    }

    var preferredPin = getSelectedBoardPin()
    if ( preferredPin === null || ! getBoardCheckEntry( preferredPin ) )
      preferredPin = boardRoutine.currentPin
    if ( preferredPin === null || ! getBoardCheckEntry( preferredPin ) )
      preferredPin = getSelectedPin()
    if ( preferredPin === null || ! getBoardCheckEntry( preferredPin ) )
      preferredPin = nextPendingBoardPin( null )
    if ( preferredPin === null )
      preferredPin = items[ 0 ].pin

    var options = []
    for ( var index in items )
    {
      var item = items[ index ]
      options.push(
        '<option value="'
        + item.pin
        + '">B'
        + item.pin
        + " | Board "
        + item.boardIndex
        + " | "
        + capitalize( item.side )
        + " | "
        + capitalize( item.status )
        + "</option>"
      )
    }

    select.html( options.join( "" ) )
    select.prop( "disabled", ! lastState || ! lastState.enabled || 0 == items.length )
    setSelectedBoardPin( preferredPin )
    if ( getSelectedBoardPin() === null )
      setSelectedBoardPin( items[ 0 ].pin )
    renderBoardSelectionDetails()
  }

  function boardRoutineStartPin()
  {
    var selectedPin = getSelectedBoardPin()
    if ( getBoardCheckEntry( selectedPin ) )
      return selectedPin

    selectedPin = getSelectedPin()
    if ( getBoardCheckEntry( selectedPin ) )
      return selectedPin

    var pendingPin = nextPendingBoardPin( null )
    if ( pendingPin !== null )
      return pendingPin

    var items = getBoardCheckItems()
    if ( 0 == items.length )
      return null

    return items[ 0 ].pin
  }

  function renderBoardRoutineSummary()
  {
    var button = $( "#manualCalibrationBoardRoutineButton" )
    var summary = $( "#manualCalibrationBoardRoutineSummary" )

    if ( ! lastState || ! lastState.enabled || lastState.mode != "uv" )
    {
      button.text( "Start Board Check" ).prop( "disabled", true )
      summary.text( "Load a U or V layer to use the board-check assistant." )
      return
    }

    if ( ! lastState.counts.bootstrapComplete )
    {
      button.text( "Start Board Check" ).prop( "disabled", true )
      summary.text( "Complete the 12 bootstrap pins before starting board checks." )
      return
    }

    if ( 0 == getBoardCheckItems().length )
    {
      button.text( "Start Board Check" ).prop( "disabled", true )
      summary.text( "No board endpoints are available for this layer." )
      return
    }

    button.prop( "disabled", ! lastState.movementReady )

    if ( boardRoutine.active && boardRoutine.currentPin !== null )
    {
      button.text( "Re-Move Current Pin" )
      summary.text( "Assistant open at B" + boardRoutine.currentPin + "." )
      return
    }

    var selectedPin = getSelectedBoardPin()
    if ( ! getBoardCheckEntry( selectedPin ) )
      selectedPin = getSelectedPin()
    if ( getBoardCheckEntry( selectedPin ) )
    {
      button.text( "Start From Selected" )
      summary.text( "Assistant will start at the selected endpoint B" + selectedPin + "." )
      return
    }

    var pendingPin = nextPendingBoardPin( null )
    if ( pendingPin !== null )
    {
      button.text( "Start Board Check" )
      summary.text( "Next pending endpoint: B" + pendingPin + "." )
      return
    }

    button.text( "Review Board Checks" )
    summary.text( "All board endpoints are marked. Start again to review them from the first endpoint." )
  }

  function closeBoardRoutine()
  {
    boardRoutine.active = false
    boardRoutine.currentPin = null
    $( "#manualCalibrationBoardDialog" ).addClass( "hidden" )
  }

  function gotoPinAction( pin, callback )
  {
    manualAction
    (
      "process.manualCalibration.gotoPin( " + pin + ", " + currentVelocity() + " )",
      function()
      {
        setMessage( "Move requested for B" + pin + ".", "success" )
        refreshPrediction( false )
        if ( callback )
          callback()
      }
    )
  }

  function capturePinAction( pin, callback )
  {
    manualAction
    (
      "process.manualCalibration.captureCurrentPin( " + pin + " )",
      function()
      {
        setMessage( "Captured B" + pin + ".", "success" )
        refreshStateOnce
        (
          function()
          {
            setSelectedPin( pin, true )
            if ( callback )
              callback()
          }
        )
      }
    )
  }

  function markPinOkAction( pin, callback )
  {
    manualAction
    (
      'process.manualCalibration.markBoardCheck( ' + pin + ', "ok" )',
      function()
      {
        setMessage( "Marked B" + pin + " OK.", "success" )
        refreshStateOnce
        (
          function()
          {
            setSelectedPin( pin, false )
            if ( callback )
              callback()
          }
        )
      }
    )
  }

  function moveBoardRoutineToPin( pin )
  {
    boardRoutine.active = true
    boardRoutine.currentPin = pin
    $( "#manualCalibrationBoardDialog" ).removeClass( "hidden" )
    setSelectedBoardPin( pin )
    setSelectedPin( pin, true )
    renderBoardRoutine()
    gotoPinAction
    (
      pin,
      function()
      {
        renderBoardRoutine()
      }
    )
  }

  function advanceBoardRoutine()
  {
    var nextPin = nextPendingBoardPin( boardRoutine.currentPin )
    if ( nextPin === null )
    {
      closeBoardRoutine()
      renderBoardRoutineSummary()
      setMessage( "Board check routine complete.", "success" )
      return
    }

    moveBoardRoutineToPin( nextPin )
  }

  function renderBoardRoutine()
  {
    var dialog = $( "#manualCalibrationBoardDialog" )
    if ( ! boardRoutine.active || boardRoutine.currentPin === null )
    {
      dialog.addClass( "hidden" )
      return
    }

    var entry = getBoardCheckEntry( boardRoutine.currentPin )
    if ( ! entry )
    {
      closeBoardRoutine()
      renderBoardRoutineSummary()
      return
    }

    var index = getBoardCheckIndex( entry.pin )
    var remaining = 0
    var items = getBoardCheckItems()
    for ( var itemIndex in items )
    {
      if ( items[ itemIndex ].status == "pending" )
        remaining += 1
    }

    $( "#manualCalibrationBoardDialogStep" )
      .text( "Endpoint " + ( index + 1 ) + " of " + items.length + "  |  B" + entry.pin )
    $( "#manualCalibrationBoardDialogBoard" )
      .text( "Board " + entry.boardIndex + " / " + capitalize( entry.side ) )
    $( "#manualCalibrationBoardDialogWire" )
      .text( formatPair( entry.predictedWireX, entry.predictedWireY ) )
    $( "#manualCalibrationBoardDialogCamera" )
      .text( formatPair( entry.predictedCameraX, entry.predictedCameraY ) )
    $( "#manualCalibrationBoardDialogRemaining" )
      .text( remaining + " pending" )
    $( "#manualCalibrationBoardDialogTag" )
      .html( statusTag( entry.status ) )
    $( "#manualCalibrationBoardDialogStatus" )
      .text( "The assistant moves to the predicted camera target, then waits for you to accept or capture." )

    if ( motorStatus && motorStatus.motor )
    {
      $( "#manualCalibrationBoardDialogMachine" )
        .text( formatPair( motorStatus.motor[ "xPosition" ], motorStatus.motor[ "yPosition" ] ) )
    }
    else
      $( "#manualCalibrationBoardDialogMachine" ).text( "-" )

    if ( ! lastState || ! lastState.movementReady )
    {
      $( "#manualCalibrationBoardDialogInstruction" )
        .text( "Waiting for motion to finish. Accept and capture are disabled until the machine is ready." )
    }
    else if ( entry.status == "adjusted" )
    {
      $( "#manualCalibrationBoardDialogInstruction" )
        .text( "This endpoint already has an adjusted measurement. Reposition if needed, then capture again to overwrite it." )
    }
    else if ( entry.status == "ok" )
    {
      $( "#manualCalibrationBoardDialogInstruction" )
        .text( "This endpoint is already accepted. You can re-move to it, or reposition and capture a new location to adjust it." )
    }
    else
    {
      $( "#manualCalibrationBoardDialogInstruction" )
        .text( "Use the page motion controls to refine the location, then accept the prediction or capture the current machine position." )
    }

    var canMutate = !! lastState && lastState.enabled && lastState.movementReady
    $( "#manualCalibrationBoardDialogMoveButton" ).prop( "disabled", ! canMutate )
    $( "#manualCalibrationBoardDialogAcceptButton" ).prop( "disabled", ! canMutate )
    $( "#manualCalibrationBoardDialogCaptureButton" ).prop( "disabled", ! canMutate )
    $( "#manualCalibrationBoardDialogNextButton" ).prop( "disabled", 0 == items.length )
    dialog.removeClass( "hidden" )
  }

  function refreshStateOnce( callback )
  {
    winder.remoteAction
    (
      "process.manualCalibration.getState()",
      function( state )
      {
        if ( state )
        {
          renderState( state )
          if ( callback )
            callback( state )
        }
      }
    )
  }

  function manualAction( command, callback )
  {
    winder.remoteAction
    (
      command,
      function( data )
      {
        if ( data && data.ok === false )
        {
          setMessage( data.error, "error" )
          return
        }

        if ( callback )
          callback( data )
      }
    )
  }

  function refreshPrediction( forceFieldUpdate )
  {
    var pin = getSelectedPin()
    if ( ! pin || ! lastState || ! lastState.enabled || ! isUVMode() )
    {
      $( "#manualCalibrationPredictionMode" ).text( "-" )
      $( "#manualCalibrationPredictionBoard" ).text( "-" )
      $( "#manualCalibrationCameraTarget" ).text( "-" )
      return
    }

    winder.remoteAction
    (
      "process.manualCalibration.predictPin( " + pin + " )",
      function( prediction )
      {
        if ( ! prediction || prediction.ok === false )
        {
          if ( prediction && prediction.error )
            setMessage( prediction.error, "error" )
          return
        }

        $( "#manualCalibrationPredictionMode" ).text( capitalize( prediction.predictionMode ) )
        $( "#manualCalibrationPredictionBoard" )
          .text( capitalize( prediction.side ) + " / Board " + prediction.boardIndex )
        $( "#manualCalibrationCameraTarget" )
          .text( formatPair( prediction.cameraCheckX, prediction.cameraCheckY ) )

        if ( forceFieldUpdate || ! suppressWireRefresh )
        {
          setFieldValueIfIdle( "#manualCalibrationWireX", formatNumber( prediction.wireX, 3 ), suppressWireRefresh )
          setFieldValueIfIdle( "#manualCalibrationWireY", formatNumber( prediction.wireY, 3 ), suppressWireRefresh )
        }
      }
    )
  }

  function renderBootstrapTable( items )
  {
    var body = $( "#manualCalibrationBootstrapTable tbody" )
    if ( ! items || 0 == items.length )
    {
      body.html( '<tr><td colspan="4">No bootstrap pins available.</td></tr>' )
      return
    }

    var rows = []
    for ( var index in items )
    {
      var item = items[ index ]
      rows.push(
        "<tr>"
        + "<td>" + item.pin + "</td>"
        + "<td>" + capitalize( item.side ) + "</td>"
        + "<td>" + statusTag( item.status ) + "</td>"
        + "<td>" + workflowButtons( item.pin ) + "</td>"
        + "</tr>"
      )
    }

    body.html( rows.join( "" ) )
  }

  function renderBoardTable( items )
  {
    renderBoardDropdown( items )
  }

  function renderMeasurementsTable( items )
  {
    var body = $( "#manualCalibrationMeasurementsTable tbody" )
    if ( ! items || 0 == items.length )
    {
      body.html( '<tr><td colspan="7">No B-pin measurements recorded.</td></tr>' )
      return
    }

    var rows = []
    for ( var index in items )
    {
      var item = items[ index ]
      rows.push(
        "<tr>"
        + "<td>" + item.pin + "</td>"
        + "<td>" + formatPair( item.rawCameraX, item.rawCameraY ) + "</td>"
        + "<td>" + formatPair( item.wireX, item.wireY ) + "</td>"
        + "<td>" + capitalize( item.source ) + "</td>"
        + "<td>" + statusTag( item.status || "pending" ) + "</td>"
        + "<td>" + item.updatedAt + "</td>"
        + '<td><button type="button" data-action="edit" data-pin="' + item.pin + '">Edit</button></td>'
        + "</tr>"
      )
    }

    body.html( rows.join( "" ) )
  }

  function setModeVisibility( state )
  {
    var isGX = !! state && state.mode == "gx"

    $( "#manualCalibrationUVControls" ).toggleClass( "hidden", isGX )
    $( "#manualCalibrationGXControls" ).toggleClass( "hidden", ! isGX )
    $( "#manualCalibrationUVInstructions" ).toggleClass( "hidden", isGX )
    $( "#manualCalibrationGXInstructions" ).toggleClass( "hidden", ! isGX )
    $( "#manualCalibrationUVWorkspace" ).toggleClass( "hidden", isGX )
    $( "#manualCalibrationGXWorkspace" ).toggleClass( "hidden", ! isGX )
    $( "#manualCalibrationUVMeasurements" ).toggleClass( "hidden", isGX )
    $( "#manualCalibrationGXMeasurements" ).toggleClass( "hidden", ! isGX )
    $( "#manualCalibrationRightColumn" ).toggleClass( "hidden", isGX )
  }

  function renderGXReferenceEditor( forceFieldUpdate )
  {
    var referenceId = getSelectedReferenceId()
    var entry = getReferenceEntry( referenceId )

    $( "#manualCalibrationGotoReferenceButton" ).text( "Go to " + referenceLabel( referenceId ) )
    $( "#manualCalibrationReferencePin" ).text( referenceLabel( referenceId ) )
    $( "#manualCalibrationReferenceCamera" )
      .text( entry ? formatPair( entry.rawCameraX, entry.rawCameraY ) : "-" )
    $( "#manualCalibrationReferenceSource" )
      .text( entry && entry.source ? capitalize( entry.source ) : "-" )
    $( "#manualCalibrationReferenceUpdatedAt" )
      .text( entry && entry.updatedAt ? "Updated: " + entry.updatedAt : "No reference recorded." )

    if ( forceFieldUpdate || ! suppressWireRefresh )
    {
      setFieldValueIfIdle(
        "#manualCalibrationReferenceWireX",
        entry && $.isNumeric( entry.wireX ) ? formatNumber( entry.wireX, 3 ) : "",
        suppressWireRefresh
      )
      setFieldValueIfIdle(
        "#manualCalibrationReferenceWireY",
        entry && $.isNumeric( entry.wireY ) ? formatNumber( entry.wireY, 3 ) : "",
        suppressWireRefresh
      )
    }
  }

  function renderGXReferenceTable( references )
  {
    var body = $( "#manualCalibrationReferenceTable tbody" )
    if ( ! references )
    {
      body.html( '<tr><td colspan="6">No reference points recorded.</td></tr>' )
      return
    }

    var rows = []
    ;[ "head", "foot" ].forEach
    (
      function( referenceId )
      {
        var item = references[ referenceId ] || {}
        rows.push(
          "<tr>"
          + "<td>" + capitalize( referenceId ) + "</td>"
          + "<td>" + referenceLabel( referenceId ) + "</td>"
          + "<td>" + formatPair( item.rawCameraX, item.rawCameraY ) + "</td>"
          + "<td>" + formatPair( item.wireX, item.wireY ) + "</td>"
          + "<td>" + capitalize( item.source ) + "</td>"
          + "<td>" + ( item.updatedAt || "-" ) + "</td>"
          + "</tr>"
        )
      }
    )

    body.html( rows.join( "" ) )
  }

  function renderGXState( state )
  {
    setFieldValueIfIdle(
      "#manualCalibrationHeadAOffset",
      $.isNumeric( state.offsets.headA ) ? formatNumber( state.offsets.headA, 3 ) : "",
      false
    )
    setFieldValueIfIdle(
      "#manualCalibrationHeadBOffset",
      $.isNumeric( state.offsets.headB ) ? formatNumber( state.offsets.headB, 3 ) : "",
      false
    )
    setFieldValueIfIdle(
      "#manualCalibrationFootAOffset",
      $.isNumeric( state.offsets.footA ) ? formatNumber( state.offsets.footA, 3 ) : "",
      false
    )
    setFieldValueIfIdle(
      "#manualCalibrationFootBOffset",
      $.isNumeric( state.offsets.footB ) ? formatNumber( state.offsets.footB, 3 ) : "",
      false
    )
    $( "#manualCalibrationTransferPause" ).prop( "checked", !! state.transferPause )
    $( "#manualCalibrationIncludeLeadMode" ).prop( "checked", !! state.includeLeadMode )
    $( "#manualCalibrationGenerateButton" ).text( "Generate " + ( state.layer || "X" ) + "-layer.gc" )
    $( "#manualCalibrationReferenceCount" )
      .text(
        "References: "
        + state.counts.referencePointsRecorded
        + " / "
        + state.counts.referencePointsTotal
      )
    $( "#manualCalibrationWrapCount" )
      .text(
        "Wraps: "
        + state.wrapCount
        + "  |  Wire spacing: "
        + formatNumber( state.wireSpacing, 6 )
      )
    $( "#manualCalibrationGenerateStatus" )
      .text( "Ready to generate: " + ( state.readyToGenerate ? "Yes" : "No" ) )
    $( "#manualCalibrationGXOutputFile" ).text( state.liveFile || "-" )
    $( "#manualCalibrationGXHash" )
      .text( state.generated && state.generated.hashValue ? state.generated.hashValue : "-" )
    $( "#manualCalibrationGXUpdatedAt" )
      .text( state.generated && state.generated.updatedAt ? state.generated.updatedAt : "-" )
    renderGXReferenceTable( state.references )
    renderGXReferenceEditor( false )
  }

  function setControlsDisabled( disabled )
  {
    $( ".manualCalibrationControlsGroup" ).toggleClass( "disabled", disabled )
    $( ".manualCalibrationControlsGroup button, .manualCalibrationControlsGroup input, .manualCalibrationControlsGroup select" )
      .prop( "disabled", disabled )
    $( "#manualCalibrationMeasurementsTable button" ).prop( "disabled", disabled )
  }

  function renderState( state )
  {
    lastState = state
    setModeVisibility( state )

    $( "#manualCalibrationLayer" ).text( state.layer || "-" )
    $( "#manualCalibrationBaseline" )
      .text( state.mode == "gx" ? "Direct G-Code" : baselineLabel( state.baselineSource ) )
    $( "#manualCalibrationDirty" ).text( state.dirty ? "Unsaved draft" : "Saved" )
    $( "#manualCalibrationMovementReady" )
      .text( state.movementReady ? "Ready for manual moves" : "Machine busy" )
    $( "#manualCalibrationLiveFile" ).text( state.liveFile || "" )
    $( "#manualCalibrationDisabled" ).text( state.disabledReason || "" )

    if ( state.enabled )
    {
      setFieldValueIfIdle(
        "#manualCalibrationOffsetX",
        formatNumber( state.cameraOffsetX, 3 ),
        suppressOffsetRefresh
      )
      setFieldValueIfIdle(
        "#manualCalibrationOffsetY",
        formatNumber( state.cameraOffsetY, 3 ),
        suppressOffsetRefresh
      )
    }

    if ( state.mode == "gx" )
    {
      closeBoardRoutine()
      renderGXState( state )
    }
    else
    {
      $( "#manualCalibrationMeasuredCount" )
        .text( "Measured pins: " + state.counts.measuredPins )
      $( "#manualCalibrationBootstrapCount" )
        .text( "Bootstrap: " + state.counts.bootstrapDone + " / " + state.counts.bootstrapTotal )
      $( "#manualCalibrationBoardCount" )
        .text( "Board checks: " + state.counts.boardCheckDone + " / " + state.counts.boardCheckTotal )
      renderBootstrapTable( state.bootstrapPins )
      renderBoardTable( state.boardChecks )
      renderMeasurementsTable( state.measuredPins )

      if ( boardRoutine.active )
      {
        if ( ! state.enabled || ! state.counts.bootstrapComplete || 0 == state.boardChecks.length )
          closeBoardRoutine()
        renderBoardRoutine()
      }

      if ( state.suggestedPin )
        $( "#manualCalibrationSuggestedPinText" ).text( "Suggested pin: B" + state.suggestedPin )
      else
        $( "#manualCalibrationSuggestedPinText" ).text( "Suggested pin: -" )

      if ( state.enabled && getSelectedPin() === null && state.suggestedPin )
        setSelectedPin( state.suggestedPin, true )
    }

    setControlsDisabled( ! state.enabled || ! state.movementReady )
    renderBoardRoutineSummary()
  }

  function applyOffsetInputs()
  {
    if ( ! lastState || ! lastState.enabled )
      return

    var xValue = parseFloat( $( "#manualCalibrationOffsetX" ).val() )
    var yValue = parseFloat( $( "#manualCalibrationOffsetY" ).val() )
    if ( isNaN( xValue ) || isNaN( yValue ) )
      return

    manualAction
    (
      "process.manualCalibration.setCameraOffset( " + xValue + ", " + yValue + " )",
      function()
      {
        refreshStateOnce()
      }
    )
  }

  function applyGXOffsetInput( offsetId, selector )
  {
    if ( ! lastState || ! lastState.enabled || ! isGXMode() )
      return

    var value = parseFloat( $( selector ).val() )
    if ( isNaN( value ) )
      return

    manualAction
    (
      'process.manualCalibration.setCornerOffset( "' + offsetId + '", ' + value + " )",
      function()
      {
        refreshStateOnce()
      }
    )
  }

  function applyTransferPause()
  {
    if ( ! lastState || ! lastState.enabled || ! isGXMode() )
      return

    manualAction
    (
      "process.manualCalibration.setTransferPause( "
      + ( $( "#manualCalibrationTransferPause" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshStateOnce()
      }
    )
  }

  function applyIncludeLeadMode()
  {
    if ( ! lastState || ! lastState.enabled || ! isGXMode() )
      return

    manualAction
    (
      "process.manualCalibration.setIncludeLeadMode( "
      + ( $( "#manualCalibrationIncludeLeadMode" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshStateOnce()
      }
    )
  }

  function captureReferenceAction( referenceId, callback )
  {
    manualAction
    (
      'process.manualCalibration.captureCurrentReference( "' + referenceId + '" )',
      function()
      {
        setMessage( "Recorded " + referenceLabel( referenceId ) + ".", "success" )
        refreshStateOnce
        (
          function()
          {
            $( "#manualCalibrationReferenceSelect" ).val( referenceId )
            renderGXReferenceEditor( true )
            if ( callback )
              callback()
          }
        )
      }
    )
  }

  function gotoReferenceAction( referenceId, callback )
  {
    manualAction
    (
      'process.manualCalibration.gotoReference( "' + referenceId + '", ' + currentVelocity() + " )",
      function()
      {
        setMessage( "Move requested for " + referenceLabel( referenceId ) + ".", "success" )
        if ( callback )
          callback()
      }
    )
  }

  function workflowAction( action, pin )
  {
    if ( action == "edit" )
    {
      setSelectedPin( pin, true )
      return
    }

    if ( action == "goto" )
    {
      gotoPinAction( pin )
      return
    }

    if ( action == "capture" )
    {
      capturePinAction( pin )
      return
    }

    if ( action == "ok" )
    {
      markPinOkAction( pin )
    }
  }

  $( "#manualCalibrationStartNewButton" )
    .click
    (
      function()
      {
        manualAction
        (
          "process.manualCalibration.startNew()",
          function()
          {
            setMessage( "Started a clean-APA draft from nominal geometry.", "success" )
            refreshStateOnce( function() { refreshPrediction( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationLoadPreviousButton" )
    .click
    (
      function()
      {
        manualAction
        (
          "process.manualCalibration.loadPrevious()",
          function()
          {
            setMessage( "Loaded the current live XML for APA recalibration.", "success" )
            refreshStateOnce( function() { refreshPrediction( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationSaveButton" )
    .click
    (
      function()
      {
        manualAction
        (
          "process.manualCalibration.saveLive()",
          function()
          {
            setMessage( "Saved the live calibration file.", "success" )
            refreshStateOnce( function() { refreshPrediction( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationClearGXButton" )
    .click
    (
      function()
      {
        manualAction
        (
          "process.manualCalibration.clearGXDraft()",
          function()
          {
            setMessage( "Cleared the X/G draft.", "success" )
            refreshStateOnce( function() { renderGXReferenceEditor( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationGenerateButton" )
    .click
    (
      function()
      {
        manualAction
        (
          "process.manualCalibration.generateRecipeFile()",
          function()
          {
            setMessage( "Generated the live " + ( lastState.layer || "X" ) + " recipe.", "success" )
            refreshStateOnce()
          }
        )
      }
    )

  $( "#manualCalibrationBoardRoutineButton" )
    .click
    (
      function()
      {
        if ( ! lastState || ! lastState.enabled )
        {
          setMessage( "Load a U or V layer first.", "error" )
          return
        }

        if ( ! lastState.counts.bootstrapComplete )
        {
          setMessage( "Complete the bootstrap pins before starting board checks.", "error" )
          return
        }

        var pin = boardRoutine.active && boardRoutine.currentPin !== null
          ? boardRoutine.currentPin
          : boardRoutineStartPin()
        if ( pin === null )
        {
          setMessage( "No board endpoints are available.", "error" )
          return
        }

        moveBoardRoutineToPin( pin )
      }
    )

  $( "#manualCalibrationReferenceSelect" )
    .change
    (
      function()
      {
        renderGXReferenceEditor( true )
      }
    )

  $( "#manualCalibrationCaptureReferenceButton" )
    .click
    (
      function()
      {
        captureReferenceAction( getSelectedReferenceId() )
      }
    )

  $( "#manualCalibrationGotoReferenceButton" )
    .click
    (
      function()
      {
        gotoReferenceAction( getSelectedReferenceId() )
      }
    )

  $( "#manualCalibrationUpdateReferenceButton" )
    .click
    (
      function()
      {
        var referenceId = getSelectedReferenceId()
        var wireX = parseFloat( $( "#manualCalibrationReferenceWireX" ).val() )
        var wireY = parseFloat( $( "#manualCalibrationReferenceWireY" ).val() )
        if ( isNaN( wireX ) || isNaN( wireY ) )
        {
          setMessage( "Enter wire-space X and Y values for the selected reference.", "error" )
          return
        }

        manualAction
        (
          'process.manualCalibration.updateReferencePoint( "'
          + referenceId
          + '", '
          + wireX
          + ", "
          + wireY
          + " )",
          function()
          {
            setMessage( "Updated " + referenceLabel( referenceId ) + ".", "success" )
            refreshStateOnce( function() { renderGXReferenceEditor( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationBoardSelect" )
    .change
    (
      function()
      {
        var pin = getSelectedBoardPin()
        renderBoardSelectionDetails()
        renderBoardRoutineSummary()
        if ( pin !== null )
          setSelectedPin( pin, true )

        if ( boardRoutine.active && pin !== null )
        {
          boardRoutine.currentPin = pin
          renderBoardRoutine()
        }
      }
    )

  $( "#manualCalibrationBoardGotoButton" )
    .click
    (
      function()
      {
        var pin = getSelectedBoardPin()
        if ( pin === null )
        {
          setMessage( "Select a board end pin first.", "error" )
          return
        }

        workflowAction( "goto", pin )
      }
    )

  $( "#manualCalibrationBoardEditButton" )
    .click
    (
      function()
      {
        var pin = getSelectedBoardPin()
        if ( pin === null )
        {
          setMessage( "Select a board end pin first.", "error" )
          return
        }

        setSelectedPin( pin, true )
      }
    )

  $( "#manualCalibrationGotoButton" )
    .click
    (
      function()
      {
        var pin = getSelectedPin()
        if ( pin === null )
        {
          setMessage( "Enter a B pin number first.", "error" )
          return
        }

        workflowAction( "goto", pin )
      }
    )

  $( "#manualCalibrationCaptureButton" )
    .click
    (
      function()
      {
        var pin = getSelectedPin()
        if ( pin === null )
        {
          setMessage( "Enter a B pin number first.", "error" )
          return
        }

        workflowAction( "capture", pin )
      }
    )

  $( "#manualCalibrationBoardDialogCloseButton" )
    .click
    (
      function()
      {
        closeBoardRoutine()
        renderBoardRoutineSummary()
      }
    )

  $( "#manualCalibrationBoardDialogMoveButton" )
    .click
    (
      function()
      {
        if ( boardRoutine.currentPin !== null )
          moveBoardRoutineToPin( boardRoutine.currentPin )
      }
    )

  $( "#manualCalibrationBoardDialogAcceptButton" )
    .click
    (
      function()
      {
        if ( boardRoutine.currentPin === null )
          return

        markPinOkAction
        (
          boardRoutine.currentPin,
          function()
          {
            advanceBoardRoutine()
          }
        )
      }
    )

  $( "#manualCalibrationBoardDialogCaptureButton" )
    .click
    (
      function()
      {
        if ( boardRoutine.currentPin === null )
          return

        capturePinAction
        (
          boardRoutine.currentPin,
          function()
          {
            advanceBoardRoutine()
          }
        )
      }
    )

  $( "#manualCalibrationBoardDialogNextButton" )
    .click
    (
      function()
      {
        if ( boardRoutine.currentPin === null )
          return

        var nextPin = nextOtherPendingBoardPin( boardRoutine.currentPin )
        if ( nextPin === null )
        {
          closeBoardRoutine()
          renderBoardRoutineSummary()
          setMessage( "No other pending board endpoints remain.", "success" )
          return
        }

        moveBoardRoutineToPin( nextPin )
      }
    )

  $( "#manualCalibrationUpdateButton" )
    .click
    (
      function()
      {
        var pin = getSelectedPin()
        var wireX = parseFloat( $( "#manualCalibrationWireX" ).val() )
        var wireY = parseFloat( $( "#manualCalibrationWireY" ).val() )
        if ( pin === null || isNaN( wireX ) || isNaN( wireY ) )
        {
          setMessage( "Select a pin and enter wire-space X and Y values.", "error" )
          return
        }

        manualAction
        (
          "process.manualCalibration.updateMeasuredPin( " + pin + ", " + wireX + ", " + wireY + " )",
          function()
          {
            setMessage( "Updated measurement for B" + pin + ".", "success" )
            refreshStateOnce( function() { refreshPrediction( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationDeleteButton" )
    .click
    (
      function()
      {
        var pin = getSelectedPin()
        if ( pin === null )
        {
          setMessage( "Select a B pin first.", "error" )
          return
        }

        manualAction
        (
          "process.manualCalibration.deleteMeasuredPin( " + pin + " )",
          function()
          {
            setMessage( "Deleted measurement for B" + pin + ".", "success" )
            refreshStateOnce( function() { refreshPrediction( true ) } )
          }
        )
      }
    )

  $( "#manualCalibrationPin" )
    .change
    (
      function()
      {
        refreshPrediction( true )
      }
    )

  $( "#manualCalibrationOffsetX, #manualCalibrationOffsetY" )
    .focus
    (
      function()
      {
        suppressOffsetRefresh = true
      }
    )
    .blur
    (
      function()
      {
        suppressOffsetRefresh = false
        applyOffsetInputs()
      }
    )
    .change( applyOffsetInputs )

  $( "#manualCalibrationHeadAOffset" ).change( function() { applyGXOffsetInput( "headA", "#manualCalibrationHeadAOffset" ) } )
  $( "#manualCalibrationHeadBOffset" ).change( function() { applyGXOffsetInput( "headB", "#manualCalibrationHeadBOffset" ) } )
  $( "#manualCalibrationFootAOffset" ).change( function() { applyGXOffsetInput( "footA", "#manualCalibrationFootAOffset" ) } )
  $( "#manualCalibrationFootBOffset" ).change( function() { applyGXOffsetInput( "footB", "#manualCalibrationFootBOffset" ) } )
  $( "#manualCalibrationTransferPause" ).change( applyTransferPause )
  $( "#manualCalibrationIncludeLeadMode" ).change( applyIncludeLeadMode )

  $( "#manualCalibrationWireX, #manualCalibrationWireY" )
    .focus
    (
      function()
      {
        suppressWireRefresh = true
      }
    )
    .blur
    (
      function()
      {
        suppressWireRefresh = false
      }
    )

  $( "#manualCalibrationReferenceWireX, #manualCalibrationReferenceWireY" )
    .focus
    (
      function()
      {
        suppressWireRefresh = true
      }
    )
    .blur
    (
      function()
      {
        suppressWireRefresh = false
      }
    )

  $( "#manualCalibrationBootstrapTable tbody" )
    .on
    (
      "click",
      "button",
      function()
      {
        workflowAction( $( this ).data( "action" ), $( this ).data( "pin" ) )
      }
    )

  $( "#manualCalibrationMeasurementsTable tbody" )
    .on
    (
      "click",
      "button",
      function()
      {
        setSelectedPin( $( this ).data( "pin" ), true )
      }
    )

  winder.addPeriodicCallback
  (
    "process.manualCalibration.getState()",
    function( state )
    {
      if ( state )
        renderState( state )
    }
  )
}
