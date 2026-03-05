function VTemplate( modules )
{
  var winder = modules.get( "Winder" )
  var activeLayer = null
  var lastRenderedLayer = null
  var lastVState = null
  var lastUState = null
  var lastManualState = null

  var vFieldSpecs = [
    { key: "top_b_foot_end", label: "Top B / foot end" },
    { key: "top_a_foot_end", label: "Top A / foot end" },
    { key: "foot_a_corner", label: "Foot A" },
    { key: "foot_b_corner", label: "Foot B" },
    { key: "bottom_b_foot_end", label: "Bottom B / foot end" },
    { key: "bottom_a_foot_end", label: "Bottom A / foot end" },
    { key: "top_a_head_end", label: "Top A / head end" },
    { key: "top_b_head_end", label: "Top B / head end" },
    { key: "head_b_corner", label: "Head B" },
    { key: "head_a_corner", label: "Head A" },
    { key: "bottom_a_head_end", label: "Bottom A / head end" },
    { key: "bottom_b_head_end", label: "Bottom B / head end" }
  ]

  var uFieldSpecs = [
    { key: "top_b_foot_end", label: "Top B / foot end" },
    { key: "top_a_foot_end", label: "Top A / foot end" },
    { key: "bottom_a_head_end", label: "Bottom A / head end" },
    { key: "bottom_b_head_end", label: "Bottom B / head end" },
    { key: "head_b_corner", label: "Head B" },
    { key: "head_a_corner", label: "Head A" },
    { key: "top_a_head_end", label: "Top A / head end" },
    { key: "top_b_head_end", label: "Top B / head end" },
    { key: "bottom_b_foot_end", label: "Bottom B / foot end" },
    { key: "bottom_a_foot_end", label: "Bottom A / foot end" },
    { key: "foot_a_corner", label: "Foot A" },
    { key: "foot_b_corner", label: "Foot B" }
  ]

  var gxOffsetSpecs = [
    { key: "headA", selector: "#gCodeGenerationGXHeadAOffset" },
    { key: "headB", selector: "#gCodeGenerationGXHeadBOffset" },
    { key: "footA", selector: "#gCodeGenerationGXFootAOffset" },
    { key: "footB", selector: "#gCodeGenerationGXFootBOffset" }
  ]

  function isGXLayer( layer )
  {
    return layer == "X" || layer == "G"
  }

  function formatInputNumber( value, decimals )
  {
    if ( ! $.isNumeric( value ) )
      return ""

    var multiplier = Math.pow( 10, decimals )
    value = Math.round( value * multiplier ) / multiplier
    return value.toFixed( decimals )
  }

  function formatDisplayNumber( value, decimals )
  {
    if ( ! $.isNumeric( value ) )
      return "-"

    return formatInputNumber( value, decimals )
  }

  function formatPair( xValue, yValue, decimals )
  {
    if ( ! $.isNumeric( xValue ) || ! $.isNumeric( yValue ) )
      return "-"

    return "X " + formatDisplayNumber( xValue, decimals )
      + "  Y " + formatDisplayNumber( yValue, decimals )
  }

  function capitalize( text )
  {
    if ( ! text )
      return "-"

    return text.charAt( 0 ).toUpperCase() + text.slice( 1 )
  }

  function gxReferenceRecorded( reference )
  {
    return !! reference
      && reference.wireX !== null
      && reference.wireY !== null
      && reference.offsetX !== null
      && reference.offsetY !== null
  }

  function setMessage( text, cssClass )
  {
    var tag = $( "#gCodeGenerationMessage" )
    tag.removeClass( "error" ).removeClass( "success" )

    if ( cssClass )
      tag.addClass( cssClass )

    tag.text( text || "" )
  }

  function setFieldValueIfIdle( selector, value )
  {
    var tag = $( selector )
    if ( document.activeElement !== tag.get( 0 ) )
      tag.val( value )
  }

  function setControlsDisabled( selector, disabled )
  {
    $( selector ).toggleClass( "disabled", disabled )
    $( selector + " button, " + selector + " input" ).prop( "disabled", disabled )
  }

  function buildOffsetFields( containerSelector, specs, inputPrefix )
  {
    var rows = []
    for ( var index in specs )
    {
      var field = specs[ index ]
      rows.push(
        '<div class="gCodeGenerationFieldStack">'
        + '<label for="' + inputPrefix + field.key + '">' + field.label + '</label>'
        + '<input type="number" id="' + inputPrefix + field.key + '" step="0.5" />'
        + "</div>"
      )
    }

    $( containerSelector ).html( rows.join( "" ) )
  }

  function setNotes( notes )
  {
    if ( ! notes || 0 == notes.length )
      notes = [ "No notes available." ]

    var items = []
    for ( var index in notes )
      items.push( "<li>" + notes[ index ] + "</li>" )

    $( "#gCodeGenerationNotes" ).html( items.join( "" ) )
  }

  function setStatus( values )
  {
    $( "#gCodeGenerationLayer" ).text( values.layer || "-" )
    $( "#gCodeGenerationMode" ).text( values.mode || "-" )
    $( "#gCodeGenerationDirty" ).text( values.dirty || "-" )
    $( "#gCodeGenerationMovementReady" ).text( values.machine || "-" )
    $( "#gCodeGenerationSummary" ).text( values.summary || "-" )
    $( "#gCodeGenerationReady" ).text( values.ready || "-" )
    $( "#gCodeGenerationLiveFile" ).text( values.liveFile || "" )
    $( "#gCodeGenerationHash" ).text( values.hash || "-" )
    $( "#gCodeGenerationUpdatedAt" ).text( values.updatedAt || "-" )
    $( "#gCodeGenerationDisabled" ).text( values.disabled || "" )
  }

  function setHeader( heading, subheading )
  {
    $( "#gCodeGenerationHeading" ).text( heading )
    $( "#gCodeGenerationSubheading" ).text( subheading || "" )
  }

  function setInfoCard( title, text )
  {
    $( "#gCodeGenerationInfoTitle" ).text( title )
    $( "#gCodeGenerationInfoText" ).text( text || "" )
  }

  function setModeVisibility( mode, showCalibrate )
  {
    $( "#gCodeGenerationVCard" ).toggleClass( "hidden", mode != "v" )
    $( "#gCodeGenerationUCard" ).toggleClass( "hidden", mode != "u" )
    $( "#gCodeGenerationGXCard" ).toggleClass( "hidden", mode != "gx" )
    $( "#gCodeGenerationInfoCard" ).toggleClass( "hidden", mode != "info" )
    $( "#gCodeGenerationOpenCalibrateButton" ).toggleClass( "hidden", ! showCalibrate )
  }

  function renderGXReference( prefix, reference )
  {
    var recorded = gxReferenceRecorded( reference )
    var statusText = recorded
      ? (
        reference.source == "loaded"
          ? "Loaded from current calibration"
          : "Recorded via " + capitalize( reference.source )
      )
      : "Pending"
    var wireText = recorded
      ? reference.pinName + "  |  " + formatPair( reference.wireX, reference.wireY, 3 )
      : "Record this reference on Calibrate."
    var rawCameraText = $.isNumeric( reference.rawCameraX ) && $.isNumeric( reference.rawCameraY )
      ? "Camera  " + formatPair( reference.rawCameraX, reference.rawCameraY, 3 )
      : "Camera  -"
    var updatedText = reference.source == "loaded"
      ? (
        reference.updatedAt
          ? "Loaded: " + reference.updatedAt
          : "Loaded from current calibration."
      )
      : (
        reference.updatedAt
          ? "Updated: " + reference.updatedAt
          : "No reference recorded."
      )

    $( "#gCodeGenerationGX" + prefix + "Status" ).text( statusText )
    $( "#gCodeGenerationGX" + prefix + "Wire" ).text( wireText )
    $( "#gCodeGenerationGX" + prefix + "RawCamera" ).text( rawCameraText )
    $( "#gCodeGenerationGX" + prefix + "Updated" ).text( updatedText )
  }

  function renderVState( state )
  {
    setModeVisibility( "v", false )
    setHeader(
      "GCode Generation",
      "Active layer V uses the direct V template generator."
    )

    if ( ! state || state.layer != "V" )
    {
      setStatus(
        {
          layer: "V",
          mode: "V template",
          dirty: "-",
          machine: "-",
          summary: "Loading V generator state...",
          ready: "-",
          liveFile: "",
          hash: "-",
          updatedAt: "-",
          disabled: "",
        }
      )
      setControlsDisabled( "#gCodeGenerationVCard", true )
      setNotes(
        [
          "Edit the 12 V offsets and transition options after the V generator state finishes loading.",
          "Generation writes the live V-layer.gc file for the active APA."
        ]
      )
      return
    }

    for ( var index in vFieldSpecs )
    {
      var field = vFieldSpecs[ index ]
      setFieldValueIfIdle(
        "#gCodeGenerationV_" + field.key,
        formatInputNumber( state.offsets[ field.key ], 3 )
      )
    }

    $( "#gCodeGenerationVTransferPause" ).prop( "checked", !! state.transferPause )
    $( "#gCodeGenerationVIncludeLeadMode" ).prop( "checked", !! state.includeLeadMode )
    setControlsDisabled( "#gCodeGenerationVCard", ! state.enabled || ! state.movementReady )

    setStatus(
      {
        layer: state.layer || "V",
        mode: "V template",
        dirty: state.dirty ? "Unsaved draft" : "Saved",
        machine: state.movementReady ? "Ready to generate" : "Machine busy",
        summary: state.wrapCount + " wraps  |  " + state.lineCount + " lines",
        ready: state.enabled && state.movementReady ? "Ready to generate" : "Waiting for machine",
        liveFile: state.liveFile || "",
        hash: state.generated && state.generated.hashValue ? state.generated.hashValue : "-",
        updatedAt: state.generated && state.generated.updatedAt ? state.generated.updatedAt : "-",
        disabled: state.movementReady
          ? ( state.disabledReason || "" )
          : "Machine is not ready to generate the V recipe.",
      }
    )

    setNotes(
      [
        "Adjust the 12 V offsets plus optional transfer pause and include-lead-mode, then generate the live V-layer.gc file.",
        "The generated recipe includes N-line numbering and wrap-level identifiers on each emitted line.",
        "The header hash updates each time the file is regenerated."
      ]
    )
  }

  function renderUState( state )
  {
    setModeVisibility( "u", false )
    setHeader(
      "GCode Generation",
      "Active layer U uses the direct U template generator."
    )

    if ( ! state || state.layer != "U" )
    {
      setStatus(
        {
          layer: "U",
          mode: "U template",
          dirty: "-",
          machine: "-",
          summary: "Loading U generator state...",
          ready: "-",
          liveFile: "",
          hash: "-",
          updatedAt: "-",
          disabled: "",
        }
      )
      setControlsDisabled( "#gCodeGenerationUCard", true )
      setNotes(
        [
          "Edit the 12 U offsets and transition options after the U generator state finishes loading.",
          "Generation writes the live U-layer.gc file for the active APA."
        ]
      )
      return
    }

    for ( var index in uFieldSpecs )
    {
      var field = uFieldSpecs[ index ]
      setFieldValueIfIdle(
        "#gCodeGenerationU_" + field.key,
        formatInputNumber( state.offsets[ field.key ], 3 )
      )
    }

    $( "#gCodeGenerationUTransferPause" ).prop( "checked", !! state.transferPause )
    $( "#gCodeGenerationUIncludeLeadMode" ).prop( "checked", !! state.includeLeadMode )
    setControlsDisabled( "#gCodeGenerationUCard", ! state.enabled || ! state.movementReady )

    setStatus(
      {
        layer: state.layer || "U",
        mode: "U template",
        dirty: state.dirty ? "Unsaved draft" : "Saved",
        machine: state.movementReady ? "Ready to generate" : "Machine busy",
        summary: state.wrapCount + " wraps  |  " + state.lineCount + " lines",
        ready: state.enabled && state.movementReady ? "Ready to generate" : "Waiting for machine",
        liveFile: state.liveFile || "",
        hash: state.generated && state.generated.hashValue ? state.generated.hashValue : "-",
        updatedAt: state.generated && state.generated.updatedAt ? state.generated.updatedAt : "-",
        disabled: state.movementReady
          ? ( state.disabledReason || "" )
          : "Machine is not ready to generate the U recipe.",
      }
    )

    setNotes(
      [
        "Adjust the 12 U offsets plus optional transfer pause and include-lead-mode, then generate the live U-layer.gc file.",
        "The generated recipe includes N-line numbering and wrap-level identifiers on each emitted line.",
        "The header hash updates each time the file is regenerated."
      ]
    )
  }

  function renderGXState( state )
  {
    setModeVisibility( "gx", true )
    setHeader(
      "GCode Generation",
      "Active layer " + activeLayer + " uses the X/G template generator."
    )
    $( "#gCodeGenerationGXHeading" ).text( activeLayer + " Parameters" )
    $( "#gCodeGenerationGXGenerateButton" ).text( "Generate " + activeLayer + "-layer.gc" )

    if ( ! state || state.layer != activeLayer || state.mode != "gx" )
    {
      renderGXReference(
        "Head",
        {
          pinName: "B960",
          rawCameraX: null,
          rawCameraY: null,
          offsetX: null,
          offsetY: null,
          wireX: null,
          wireY: null,
          updatedAt: "",
          source: null,
        }
      )
      renderGXReference(
        "Foot",
        {
          pinName: "B1",
          rawCameraX: null,
          rawCameraY: null,
          offsetX: null,
          offsetY: null,
          wireX: null,
          wireY: null,
          updatedAt: "",
          source: null,
        }
      )
      for ( var index in gxOffsetSpecs )
        setFieldValueIfIdle( gxOffsetSpecs[ index ].selector, "" )

      $( "#gCodeGenerationGXTransferPause" ).prop( "checked", false )
      setControlsDisabled( "#gCodeGenerationGXCard", true )

      setStatus(
        {
          layer: activeLayer || "-",
          mode: "X/G template",
          dirty: "-",
          machine: "-",
          summary: "Loading X/G generator state...",
          ready: "-",
          liveFile: "",
          hash: "-",
          updatedAt: "-",
          disabled: "",
        }
      )

      setNotes(
        [
          "Capture or edit the head and foot references on Calibrate, then return here to generate the active X/G recipe.",
          "The X/G generator state is still loading."
        ]
      )
      return
    }

    renderGXReference( "Head", state.references.head )
    renderGXReference( "Foot", state.references.foot )

    for ( var fieldIndex in gxOffsetSpecs )
    {
      var gxField = gxOffsetSpecs[ fieldIndex ]
      setFieldValueIfIdle(
        gxField.selector,
        formatInputNumber( state.offsets[ gxField.key ], 3 )
      )
    }

    $( "#gCodeGenerationGXTransferPause" ).prop( "checked", !! state.transferPause )
    setControlsDisabled( "#gCodeGenerationGXCard", ! state.enabled || ! state.movementReady )

    setStatus(
      {
        layer: state.layer || activeLayer,
        mode: state.layer + " template",
        dirty: state.dirty ? "Unsaved draft" : "Saved",
        machine: state.movementReady ? "Ready to generate" : "Machine busy",
        summary:
          state.wrapCount
          + " wraps  |  "
          + state.counts.referencePointsRecorded
          + " / "
          + state.counts.referencePointsTotal
          + " refs",
        ready: state.readyToGenerate ? "Ready to generate" : "Waiting for references / offsets",
        liveFile: state.liveFile || "",
        hash: state.generated && state.generated.hashValue ? state.generated.hashValue : "-",
        updatedAt: state.generated && state.generated.updatedAt ? state.generated.updatedAt : "-",
        disabled: state.movementReady
          ? ""
          : "Machine is not ready to update the X/G draft.",
      }
    )

    setNotes(
      [
        "Capture or edit the head and foot references on Calibrate, then return here to adjust offsets or generate the live recipe.",
        "Clear Draft resets the active layer's X/G references, offsets, and transfer pause values.",
        "Transfer Pause inserts the same hold points used by the manual X/G generator."
      ]
    )
  }

  function renderGXCalibrateState( state )
  {
    setModeVisibility( "info", true )
    setHeader(
      "GCode Generation",
      "Active layer " + activeLayer + " is generated from the Calibrate tab."
    )
    setInfoCard(
      activeLayer + " Layer Uses Calibrate",
      "Use Calibrate to go to B960/B1, record the head and foot references, set the four corner offsets, and generate the live "
      + activeLayer
      + "-layer.gc file."
    )

    if ( ! state || state.layer != activeLayer || state.mode != "gx" )
    {
      setStatus(
        {
          layer: activeLayer || "-",
          mode: "Calibration workflow",
          dirty: "-",
          machine: "-",
          summary: "Loading X/G calibration state...",
          ready: "-",
          liveFile: "",
          hash: "-",
          updatedAt: "-",
          disabled: "Open Calibrate to work on the active X/G recipe.",
        }
      )
      setNotes(
        [
          "Use Calibrate to move to the current X/G reference pin, record the head and foot points, and generate the active recipe.",
          "This page intentionally hides the X/G generation controls."
        ]
      )
      return
    }

    setStatus(
      {
        layer: state.layer || activeLayer,
        mode: state.layer + " calibration",
        dirty: state.dirty ? "Unsaved draft" : "Saved",
        machine: state.movementReady ? "Ready for calibration" : "Machine busy",
        summary:
          state.wrapCount
          + " wraps  |  "
          + state.counts.referencePointsRecorded
          + " / "
          + state.counts.referencePointsTotal
          + " refs",
        ready: state.readyToGenerate ? "Generate on Calibrate" : "Complete setup on Calibrate",
        liveFile: state.liveFile || "",
        hash: state.generated && state.generated.hashValue ? state.generated.hashValue : "-",
        updatedAt: state.generated && state.generated.updatedAt ? state.generated.updatedAt : "-",
        disabled: "Use the Calibrate tab to generate the live " + state.layer + "-layer.gc file.",
      }
    )

    setNotes(
      [
        "Use Calibrate to move to B960/B1, record the head and foot references, edit corner offsets, and generate the live "
        + state.layer
        + "-layer.gc file.",
        "This page shows the current X/G draft status only. The X/G generation controls live on Calibrate."
      ]
    )
  }

  function renderInfoState( layer, state )
  {
    setModeVisibility( "info", false )

    setHeader(
      "GCode Generation",
      "Load a recipe to see the generator tools for its active layer."
    )
    setInfoCard(
      layer ? "Generator Unavailable" : "No Active Recipe",
      layer
        ? "No direct G-code generator is available for layer " + layer + "."
        : "Load a recipe to see the generator tools for its active layer."
    )
    setStatus(
      {
        layer: layer || "-",
        mode: layer ? "Unavailable" : "No active layer",
        dirty: "-",
        machine: state && state.movementReady ? "Ready" : "-",
        summary: layer ? "No direct generator" : "Load a recipe",
        ready: layer ? "Unavailable" : "Load a recipe",
        liveFile: "",
        hash: "-",
        updatedAt: "-",
        disabled: layer
          ? "No direct G-code generator is available for layer " + layer + "."
          : "Load a recipe to see the generator tools for its active layer.",
      }
    )

    setNotes(
      [
        "Load a recipe to detect its active layer and show the corresponding generation controls."
      ]
    )
  }

  function render()
  {
    if ( activeLayer != lastRenderedLayer )
    {
      setMessage( "" )
      lastRenderedLayer = activeLayer
    }

    if ( activeLayer == "V" )
    {
      renderVState( lastVState )
      return
    }

    if ( activeLayer == "U" )
    {
      renderUState( lastUState )
      return
    }

    if ( isGXLayer( activeLayer ) )
    {
      renderGXCalibrateState( lastManualState )
      return
    }

    renderInfoState( activeLayer, lastManualState && lastManualState.layer == activeLayer ? lastManualState : null )
  }

  function refreshLayerOnce()
  {
    winder.remoteAction
    (
      "process.getRecipeLayer()",
      function( layer )
      {
        activeLayer = layer
        render()
      }
    )
  }

  function refreshVStateOnce( callback )
  {
    winder.remoteAction
    (
      "process.vTemplateRecipe.getState()",
      function( state )
      {
        if ( state )
        {
          lastVState = state
          render()
          if ( callback )
            callback( state )
        }
      }
    )
  }

  function refreshUStateOnce( callback )
  {
    winder.remoteAction
    (
      "process.uTemplateRecipe.getState()",
      function( state )
      {
        if ( state )
        {
          lastUState = state
          render()
          if ( callback )
            callback( state )
        }
      }
    )
  }

  function refreshManualStateOnce( callback )
  {
    winder.remoteAction
    (
      "process.manualCalibration.getState()",
      function( state )
      {
        if ( state )
        {
          lastManualState = state
          render()
          if ( callback )
            callback( state )
        }
      }
    )
  }

  function pageAction( command, callback )
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

  function applyVOffsetInput( offsetId )
  {
    if ( activeLayer != "V" || ! lastVState || ! lastVState.enabled )
      return

    var value = parseFloat( $( "#gCodeGenerationV_" + offsetId ).val() )
    if ( isNaN( value ) )
    {
      refreshVStateOnce()
      return
    }

    pageAction
    (
      'process.vTemplateRecipe.setOffset( "' + offsetId + '", ' + value + " )",
      function()
      {
        refreshVStateOnce()
      }
    )
  }

  function applyVTransferPause()
  {
    if ( activeLayer != "V" || ! lastVState || ! lastVState.enabled )
      return

    pageAction
    (
      "process.vTemplateRecipe.setTransferPause( "
      + ( $( "#gCodeGenerationVTransferPause" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshVStateOnce()
      }
    )
  }

  function applyVIncludeLeadMode()
  {
    if ( activeLayer != "V" || ! lastVState || ! lastVState.enabled )
      return

    pageAction
    (
      "process.vTemplateRecipe.setIncludeLeadMode( "
      + ( $( "#gCodeGenerationVIncludeLeadMode" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshVStateOnce()
      }
    )
  }

  function applyUOffsetInput( offsetId )
  {
    if ( activeLayer != "U" || ! lastUState || ! lastUState.enabled )
      return

    var value = parseFloat( $( "#gCodeGenerationU_" + offsetId ).val() )
    if ( isNaN( value ) )
    {
      refreshUStateOnce()
      return
    }

    pageAction
    (
      'process.uTemplateRecipe.setOffset( "' + offsetId + '", ' + value + " )",
      function()
      {
        refreshUStateOnce()
      }
    )
  }

  function applyUTransferPause()
  {
    if ( activeLayer != "U" || ! lastUState || ! lastUState.enabled )
      return

    pageAction
    (
      "process.uTemplateRecipe.setTransferPause( "
      + ( $( "#gCodeGenerationUTransferPause" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshUStateOnce()
      }
    )
  }

  function applyUIncludeLeadMode()
  {
    if ( activeLayer != "U" || ! lastUState || ! lastUState.enabled )
      return

    pageAction
    (
      "process.uTemplateRecipe.setIncludeLeadMode( "
      + ( $( "#gCodeGenerationUIncludeLeadMode" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshUStateOnce()
      }
    )
  }

  function applyGXOffsetInput( offsetId, selector )
  {
    if ( ! isGXLayer( activeLayer ) || ! lastManualState || lastManualState.mode != "gx" )
      return

    var value = parseFloat( $( selector ).val() )
    if ( isNaN( value ) )
    {
      refreshManualStateOnce()
      return
    }

    pageAction
    (
      'process.manualCalibration.setCornerOffset( "' + offsetId + '", ' + value + " )",
      function()
      {
        refreshManualStateOnce()
      }
    )
  }

  function applyGXTransferPause()
  {
    if ( ! isGXLayer( activeLayer ) || ! lastManualState || lastManualState.mode != "gx" )
      return

    pageAction
    (
      "process.manualCalibration.setTransferPause( "
      + ( $( "#gCodeGenerationGXTransferPause" ).is( ":checked" ) ? "True" : "False" )
      + " )",
      function()
      {
        refreshManualStateOnce()
      }
    )
  }

  buildOffsetFields( "#gCodeGenerationVFieldGrid", vFieldSpecs, "gCodeGenerationV_" )
  buildOffsetFields( "#gCodeGenerationUFieldGrid", uFieldSpecs, "gCodeGenerationU_" )

  for ( var index in vFieldSpecs )
  {
    ( function( offsetId )
      {
        $( "#gCodeGenerationV_" + offsetId )
          .change
          (
            function()
            {
              applyVOffsetInput( offsetId )
            }
          )
      }
    )( vFieldSpecs[ index ].key )
  }

  for ( var gxIndex in gxOffsetSpecs )
  {
    ( function( offsetId, selector )
      {
        $( selector )
          .change
          (
            function()
            {
              applyGXOffsetInput( offsetId, selector )
            }
          )
      }
    )( gxOffsetSpecs[ gxIndex ].key, gxOffsetSpecs[ gxIndex ].selector )
  }

  for ( var uIndex in uFieldSpecs )
  {
    ( function( offsetId )
      {
        $( "#gCodeGenerationU_" + offsetId )
          .change
          (
            function()
            {
              applyUOffsetInput( offsetId )
            }
          )
      }
    )( uFieldSpecs[ uIndex ].key )
  }

  $( "#gCodeGenerationVTransferPause" )
    .change
    (
      function()
      {
        applyVTransferPause()
      }
    )

  $( "#gCodeGenerationVIncludeLeadMode" )
    .change
    (
      function()
      {
        applyVIncludeLeadMode()
      }
    )

  $( "#gCodeGenerationGXTransferPause" )
    .change
    (
      function()
      {
        applyGXTransferPause()
      }
    )

  $( "#gCodeGenerationUTransferPause" )
    .change
    (
      function()
      {
        applyUTransferPause()
      }
    )

  $( "#gCodeGenerationUIncludeLeadMode" )
    .change
    (
      function()
      {
        applyUIncludeLeadMode()
      }
    )

  $( "#gCodeGenerationVResetButton" )
    .click
    (
      function()
      {
        pageAction
        (
          "process.vTemplateRecipe.resetDraft()",
          function()
          {
            setMessage( "Reset the V recipe parameters to defaults.", "success" )
            refreshVStateOnce()
          }
        )
      }
    )

  $( "#gCodeGenerationVGenerateButton" )
    .click
    (
      function()
      {
        pageAction
        (
          "process.vTemplateRecipe.generateRecipeFile()",
          function()
          {
            setMessage( "Generated the live V-layer.gc recipe.", "success" )
            refreshVStateOnce()
          }
        )
      }
    )

  $( "#gCodeGenerationUResetButton" )
    .click
    (
      function()
      {
        pageAction
        (
          "process.uTemplateRecipe.resetDraft()",
          function()
          {
            setMessage( "Reset the U recipe parameters to defaults.", "success" )
            refreshUStateOnce()
          }
        )
      }
    )

  $( "#gCodeGenerationUGenerateButton" )
    .click
    (
      function()
      {
        pageAction
        (
          "process.uTemplateRecipe.generateRecipeFile()",
          function()
          {
            setMessage( "Generated the live U-layer.gc recipe.", "success" )
            refreshUStateOnce()
          }
        )
      }
    )

  $( "#gCodeGenerationGXClearButton" )
    .click
    (
      function()
      {
        pageAction
        (
          "process.manualCalibration.clearGXDraft()",
          function()
          {
            setMessage( "Cleared the " + activeLayer + " draft.", "success" )
            refreshManualStateOnce()
          }
        )
      }
    )

  $( "#gCodeGenerationGXGenerateButton" )
    .click
    (
      function()
      {
        pageAction
        (
          "process.manualCalibration.generateRecipeFile()",
          function()
          {
            setMessage( "Generated the live " + activeLayer + "-layer.gc recipe.", "success" )
            refreshManualStateOnce()
          }
        )
      }
    )

  $( "#gCodeGenerationOpenCalibrateButton" )
    .click
    (
      function()
      {
        window.load( "/Desktop/Pages/Calibrate" )
      }
    )

  winder.addPeriodicCallback
  (
    "process.getRecipeLayer()",
    function( layer )
    {
      activeLayer = layer
      render()
    }
  )

  winder.addPeriodicCallback
  (
    "process.vTemplateRecipe.getState()",
    function( state )
    {
      if ( state )
      {
        lastVState = state
        render()
      }
    }
  )

  winder.addPeriodicCallback
  (
    "process.uTemplateRecipe.getState()",
    function( state )
    {
      if ( state )
      {
        lastUState = state
        render()
      }
    }
  )

  winder.addPeriodicCallback
  (
    "process.manualCalibration.getState()",
    function( state )
    {
      if ( state )
      {
        lastManualState = state
        render()
      }
    }
  )

  setControlsDisabled( "#gCodeGenerationVCard", true )
  setControlsDisabled( "#gCodeGenerationUCard", true )
  setControlsDisabled( "#gCodeGenerationGXCard", true )
  render()
  refreshLayerOnce()
  refreshVStateOnce()
  refreshUStateOnce()
  refreshManualStateOnce()
}
