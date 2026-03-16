function QueuedMotionPreview(modules)
{
  var winder = null
  var motorStatus = null
  var uiServices = null
  var commands = window.CommandCatalog

  var preview = null
  var decisionPending = false
  var limits = null

  var CANVAS_HEIGHT = 320
  var PADDING = 18

  function readNumber(source, key, fallback)
  {
    if ( source && source.hasOwnProperty( key ) )
    {
      var value = parseFloat( source[ key ] )
      if ( isFinite( value ) )
        return value
    }
    return fallback
  }

  function buildLimits(source)
  {
    return {
      limitLeft: readNumber( source, "limitLeft", 0.0 ),
      limitRight: readNumber( source, "limitRight", 7360.0 ),
      limitBottom: readNumber( source, "limitBottom", 0.0 ),
      limitTop: readNumber( source, "limitTop", 3000.0 ),
      transferZoneHeadMinX: readNumber( source, "transferZoneHeadMinX", 400.0 ),
      transferZoneHeadMaxX: readNumber( source, "transferZoneHeadMaxX", 500.0 ),
      transferZoneFootMinX: readNumber( source, "transferZoneFootMinX", 7100.0 ),
      transferZoneFootMaxX: readNumber( source, "transferZoneFootMaxX", 7200.0 ),
      supportCollisionBottomMinY: readNumber( source, "supportCollisionBottomMinY", 80.0 ),
      supportCollisionBottomMaxY: readNumber( source, "supportCollisionBottomMaxY", 450.0 ),
      supportCollisionMiddleMinY: readNumber( source, "supportCollisionMiddleMinY", 1050.0 ),
      supportCollisionMiddleMaxY: readNumber( source, "supportCollisionMiddleMaxY", 1550.0 ),
      supportCollisionTopMinY: readNumber( source, "supportCollisionTopMinY", 2200.0 ),
      supportCollisionTopMaxY: readNumber( source, "supportCollisionTopMaxY", 2650.0 )
    }
  }

  function activeLimits()
  {
    if ( preview && preview.limits )
      return buildLimits( preview.limits )
    return limits || buildLimits( {} )
  }

  function formatNumber(value, decimals)
  {
    if ( ! isFinite( value ) )
      return "-"
    return Number( value ).toFixed( decimals )
  }

  function formatPoint(point)
  {
    if ( ! point )
      return "( -, - )"
    return "(" + formatNumber( point.x, 1 ) + ", " + formatNumber( point.y, 1 ) + ")"
  }

  function setRows(targetId, rows, emptyText)
  {
    var target = $( targetId )
    target.empty()

    if ( ! rows || 0 === rows.length )
    {
      $( "<div />" )
        .addClass( "queuedMotionPreviewEmpty" )
        .text( emptyText )
        .appendTo( target )
      return
    }

    for ( var index = 0; index < rows.length; index += 1 )
    {
      $( "<div />" )
        .addClass( "queuedMotionPreviewRow" )
        .text( rows[ index ] )
        .appendTo( target )
    }
  }

  function updateDetails()
  {
    var summaryText = ""
    var statusText = "No queued G113 preview pending."
    var sourceRows = []
    var segmentRows = []

    if ( preview )
    {
      var firstLine = preview.sourceLines && preview.sourceLines.length > 0
        ? preview.sourceLines[ 0 ].lineNumber
        : preview.summary.startLineNumber
      var lastLine = preview.sourceLines && preview.sourceLines.length > 0
        ? preview.sourceLines[ preview.sourceLines.length - 1 ].lineNumber
        : preview.summary.startLineNumber

      if ( decisionPending )
        statusText = "Submitting queued G113 preview decision..."
      else
        statusText = "Queued G113 preview waiting for confirmation before execution."

      summaryText =
        "Lines " + firstLine + "-" + lastLine
        + " | " + preview.summary.g113Count + " G113"
        + " | " + preview.summary.segmentCount + " segments"
        + " | " + formatNumber( preview.summary.totalPathLength, 1 ) + " mm"

      if ( preview.stopAfterBlock )
        summaryText += " | single-step"

      for ( var sourceIndex = 0; sourceIndex < preview.sourceLines.length; sourceIndex += 1 )
      {
        var sourceLine = preview.sourceLines[ sourceIndex ]
        sourceRows.push( "N" + sourceLine.lineNumber + " " + sourceLine.text )
      }

      for ( var segmentIndex = 0; segmentIndex < preview.segments.length; segmentIndex += 1 )
      {
        var segment = preview.segments[ segmentIndex ]
        var segmentText =
          "#" + segment.index
          + " seq " + segment.seq
          + " " + segment.kind.toUpperCase()
          + " " + formatPoint( segment.start )
          + " -> " + formatPoint( segment.end )
          + " len " + formatNumber( segment.pathLength, 1 )
          + " speed " + formatNumber( segment.speed, 1 )
          + " term " + segment.termType

        if ( segment.circle )
        {
          segmentText +=
            " center " + formatPoint( segment.circle.center )
            + " r " + formatNumber( segment.circle.radius, 1 )
            + " " + segment.circle.directionLabel
        }

        segmentRows.push( segmentText )
      }
    }
    else
    {
      var x = motorStatus && motorStatus.motor ? parseFloat( motorStatus.motor[ "xPosition" ] ) : NaN
      var y = motorStatus && motorStatus.motor ? parseFloat( motorStatus.motor[ "yPosition" ] ) : NaN
      summaryText = "Head at " + formatPoint( { x: x, y: y } )
    }

    $( "#queuedMotionPreviewStatus" ).text( statusText )
    $( "#queuedMotionPreviewSummary" ).text( summaryText )
    $( "#queuedMotionPreviewContinueButton" ).prop( "disabled", ! preview || decisionPending )
    $( "#queuedMotionPreviewCancelButton" ).prop( "disabled", ! preview || decisionPending )

    setRows( "#queuedMotionPreviewSource", sourceRows, "No queued G113 lines are waiting." )
    setRows( "#queuedMotionPreviewSegments", segmentRows, "No queued segments are waiting." )
  }

  function ensureCanvas()
  {
    var canvas = document.getElementById( "queuedMotionPreviewCanvas" )
    if ( ! canvas )
      return null

    var width = $( canvas ).innerWidth()
    if ( ! width || width < 10 )
      width = 620

    var pixelRatio = window.devicePixelRatio || 1
    canvas.width = Math.round( width * pixelRatio )
    canvas.height = Math.round( CANVAS_HEIGHT * pixelRatio )
    canvas.style.height = CANVAS_HEIGHT + "px"

    var context = canvas.getContext( "2d" )
    context.setTransform( pixelRatio, 0, 0, pixelRatio, 0, 0 )
    context.clearRect( 0, 0, width, CANVAS_HEIGHT )

    return {
      canvas: canvas,
      context: context,
      width: width,
      height: CANVAS_HEIGHT
    }
  }

  function pointToCanvas(point, geometry, width, height)
  {
    var usableWidth = Math.max( 1, width - ( 2 * PADDING ) )
    var usableHeight = Math.max( 1, height - ( 2 * PADDING ) )
    var xSpan = Math.max( 1, geometry.limitRight - geometry.limitLeft )
    var ySpan = Math.max( 1, geometry.limitTop - geometry.limitBottom )

    return {
      x: PADDING + ( ( point.x - geometry.limitLeft ) / xSpan ) * usableWidth,
      y: height - PADDING - ( ( point.y - geometry.limitBottom ) / ySpan ) * usableHeight
    }
  }

  function drawBase(context, geometry, width, height)
  {
    context.save()
    context.strokeStyle = "rgba(148, 163, 184, 0.55)"
    context.lineWidth = 1
    context.strokeRect(
      PADDING,
      PADDING,
      width - ( 2 * PADDING ),
      height - ( 2 * PADDING )
    )

    context.fillStyle = "rgba(148, 163, 184, 0.8)"
    context.font = "12px Consolas"
    context.fillText( "Head side", PADDING + 4, 14 )
    context.fillText( "Foot side", width - 72, 14 )
    context.restore()
  }

  function supportBars(geometry)
  {
    return [
      {
        key: "FrameLockHeadTop",
        x0: geometry.transferZoneHeadMinX,
        x1: geometry.transferZoneHeadMaxX,
        y0: geometry.supportCollisionTopMinY,
        y1: geometry.supportCollisionTopMaxY,
        label: "HT"
      },
      {
        key: "FrameLockHeadMid",
        x0: geometry.transferZoneHeadMinX,
        x1: geometry.transferZoneHeadMaxX,
        y0: geometry.supportCollisionMiddleMinY,
        y1: geometry.supportCollisionMiddleMaxY,
        label: "HM"
      },
      {
        key: "FrameLockHeadBtm",
        x0: geometry.transferZoneHeadMinX,
        x1: geometry.transferZoneHeadMaxX,
        y0: geometry.supportCollisionBottomMinY,
        y1: geometry.supportCollisionBottomMaxY,
        label: "HB"
      },
      {
        key: "FrameLockFootTop",
        x0: geometry.transferZoneFootMinX,
        x1: geometry.transferZoneFootMaxX,
        y0: geometry.supportCollisionTopMinY,
        y1: geometry.supportCollisionTopMaxY,
        label: "FT"
      },
      {
        key: "FrameLockFootMid",
        x0: geometry.transferZoneFootMinX,
        x1: geometry.transferZoneFootMaxX,
        y0: geometry.supportCollisionMiddleMinY,
        y1: geometry.supportCollisionMiddleMaxY,
        label: "FM"
      },
      {
        key: "FrameLockFootBtm",
        x0: geometry.transferZoneFootMinX,
        x1: geometry.transferZoneFootMaxX,
        y0: geometry.supportCollisionBottomMinY,
        y1: geometry.supportCollisionBottomMaxY,
        label: "FB"
      }
    ]
  }

  function drawSupportBars(context, geometry, width, height)
  {
    var inputs = motorStatus && motorStatus.inputs ? motorStatus.inputs : {}
    var bars = supportBars( geometry )

    for ( var index = 0; index < bars.length; index += 1 )
    {
      var bar = bars[ index ]
      var topLeft = pointToCanvas( { x: bar.x0, y: bar.y1 }, geometry, width, height )
      var bottomRight = pointToCanvas( { x: bar.x1, y: bar.y0 }, geometry, width, height )
      var isLocked = !! inputs[ bar.key ]

      context.save()
      context.fillStyle = isLocked ? "rgba(239, 68, 68, 0.75)" : "rgba(34, 197, 94, 0.6)"
      context.strokeStyle = isLocked ? "rgba(127, 29, 29, 0.95)" : "rgba(21, 128, 61, 0.95)"
      context.lineWidth = 1.5
      context.fillRect(
        topLeft.x,
        topLeft.y,
        Math.max( 6, bottomRight.x - topLeft.x ),
        Math.max( 6, bottomRight.y - topLeft.y )
      )
      context.strokeRect(
        topLeft.x,
        topLeft.y,
        Math.max( 6, bottomRight.x - topLeft.x ),
        Math.max( 6, bottomRight.y - topLeft.y )
      )
      context.fillStyle = "rgba(255, 255, 255, 0.9)"
      context.font = "11px Consolas"
      context.fillText( bar.label, topLeft.x + 2, topLeft.y + 12 )
      context.restore()
    }
  }

  function currentHeadPosition()
  {
    if ( motorStatus && motorStatus.motor )
    {
      var x = parseFloat( motorStatus.motor[ "xPosition" ] )
      var y = parseFloat( motorStatus.motor[ "yPosition" ] )
      if ( isFinite( x ) && isFinite( y ) )
        return { x: x, y: y }
    }

    if ( preview && preview.actualHead )
      return preview.actualHead

    return null
  }

  function drawHead(context, geometry, width, height)
  {
    var head = currentHeadPosition()
    if ( ! head )
      return

    var position = pointToCanvas( head, geometry, width, height )
    context.save()
    context.fillStyle = "#f8fafc"
    context.strokeStyle = "#0f172a"
    context.lineWidth = 2
    context.beginPath()
    context.arc( position.x, position.y, 7, 0, 2 * Math.PI )
    context.fill()
    context.stroke()
    context.fillStyle = "rgba(248, 250, 252, 0.9)"
    context.font = "12px Consolas"
    context.fillText( "HEAD", position.x + 10, position.y - 10 )
    context.restore()
  }

  function arcSweep(startAngle, endAngle, direction)
  {
    var tau = 2 * Math.PI
    var ccw = ( endAngle - startAngle ) % tau
    var cw = ( startAngle - endAngle ) % tau

    if ( ccw < 0 )
      ccw += tau
    if ( cw < 0 )
      cw += tau

    if ( 0 === direction )
      return -cw
    if ( 1 === direction )
      return ccw
    if ( 2 === direction )
      return -( cw > 1e-9 ? cw : tau )
    if ( 3 === direction )
      return ccw > 1e-9 ? ccw : tau
    return null
  }

  function traceSegment(context, segment, geometry, width, height)
  {
    var start = pointToCanvas( segment.start, geometry, width, height )
    var end = pointToCanvas( segment.end, geometry, width, height )

    context.beginPath()
    context.moveTo( start.x, start.y )

    if ( "circle" === segment.kind && segment.circle )
    {
      var center = segment.circle.center
      var radius = segment.circle.radius
      var startAngle = Math.atan2( segment.start.y - center.y, segment.start.x - center.x )
      var endAngle = Math.atan2( segment.end.y - center.y, segment.end.x - center.x )
      var sweep = arcSweep( startAngle, endAngle, segment.circle.direction )

      if ( isFinite( radius ) && radius > 0 && null !== sweep )
      {
        var steps = Math.max( 8, Math.ceil( Math.abs( sweep ) / ( Math.PI / 24 ) ) )
        for ( var step = 1; step <= steps; step += 1 )
        {
          var angle = startAngle + ( sweep * ( step / steps ) )
          var point = {
            x: center.x + radius * Math.cos( angle ),
            y: center.y + radius * Math.sin( angle )
          }
          var mapped = pointToCanvas( point, geometry, width, height )
          context.lineTo( mapped.x, mapped.y )
        }
      }
      else
        context.lineTo( end.x, end.y )
    }
    else
      context.lineTo( end.x, end.y )

    context.strokeStyle = "circle" === segment.kind ? "#38bdf8" : "#f59e0b"
    context.lineWidth = 3
    context.stroke()

    context.fillStyle = context.strokeStyle
    context.beginPath()
    context.arc( end.x, end.y, 3.5, 0, 2 * Math.PI )
    context.fill()
    context.font = "11px Consolas"
    context.fillText( String( segment.index ), end.x + 5, end.y - 5 )
  }

  function drawPreview(context, geometry, width, height)
  {
    if ( ! preview || ! preview.segments || 0 === preview.segments.length )
      return

    var start = pointToCanvas( preview.start, geometry, width, height )
    context.save()
    context.strokeStyle = "#22d3ee"
    context.lineWidth = 2
    context.beginPath()
    context.arc( start.x, start.y, 9, 0, 2 * Math.PI )
    context.stroke()
    context.restore()

    for ( var index = 0; index < preview.segments.length; index += 1 )
      traceSegment( context, preview.segments[ index ], geometry, width, height )
  }

  function renderCanvas()
  {
    var canvasState = ensureCanvas()
    if ( ! canvasState )
      return

    var geometry = activeLimits()
    drawBase( canvasState.context, geometry, canvasState.width, canvasState.height )
    drawSupportBars( canvasState.context, geometry, canvasState.width, canvasState.height )
    drawPreview( canvasState.context, geometry, canvasState.width, canvasState.height )
    drawHead( canvasState.context, geometry, canvasState.width, canvasState.height )
  }

  function submitDecision(commandName)
  {
    if ( ! preview || decisionPending )
      return

    decisionPending = true
    updateDetails()

    uiServices.call(
      commandName,
      {},
      function( accepted )
      {
        if ( true !== accepted )
          decisionPending = false
        updateDetails()
      },
      function()
      {
        decisionPending = false
        updateDetails()
      }
    )
  }

  function loadGeometry()
  {
    uiServices.call(
      commands.machine.getCalibration,
      {},
      function( data )
      {
        limits = buildLimits( data || {} )
        renderCanvas()
      }
    )
  }

  function bindControls()
  {
    $( "#queuedMotionPreviewContinueButton" )
      .off( "click.queuedPreview" )
      .on( "click.queuedPreview", function() {
        submitDecision( commands.process.continueQueuedMotionPreview )
      } )

    $( "#queuedMotionPreviewCancelButton" )
      .off( "click.queuedPreview" )
      .on( "click.queuedPreview", function() {
        submitDecision( commands.process.cancelQueuedMotionPreview )
      } )
  }

  modules.load(
    [
      "/Scripts/Winder",
      "/Scripts/UiServices",
      "/Desktop/Modules/MotorStatus"
    ],
    function()
    {
      winder = modules.get( "Winder" )
      motorStatus = modules.get( "MotorStatus" )
      uiServices = modules.get( "UiServices" )
      limits = buildLimits( {} )

      bindControls()
      updateDetails()
      loadGeometry()

      winder.addPeriodicCallback(
        commands.process.getQueuedMotionPreview,
        function( data )
        {
          preview = data
          decisionPending = false
          if ( preview && preview.limits )
            limits = buildLimits( preview.limits )
          updateDetails()
          renderCanvas()
        }
      )

      winder.addPeriodicEndCallback( renderCanvas )

      $( window ).off( "resize.queuedPreview" ).on( "resize.queuedPreview", renderCanvas )
    }
  )
}
