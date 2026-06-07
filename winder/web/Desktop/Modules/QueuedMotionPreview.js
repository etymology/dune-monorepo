function QueuedMotionPreview(modules)
{
  var winder = null
  var motorStatus = null
  var uiServices = null
  var commands = null

  var preview = null
  var previewPending = false
  var decisionPending = false
  var limits = null
  var layerCalibration = null
  var autoContinue = false
  var useMaxSpeed = false
  var useMaxSpeedPending = false

  var PADDING = 18
  var LEGEND_SPACE = 22
  var MIN_VIEW_HEIGHT = 96
  var YZ_Z_AXIS_SCALE_FACTOR = 0.6
  var AUTO_CONTINUE_STORAGE_KEY = "queuedMotionPreview.autoContinue"

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
      zFront: readNumber( source, "zFront", 0.0 ),
      zBack: readNumber( source, "zBack", 400.0 ),
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
      {
        if ( autoContinue && previewPending )
          statusText = "Auto-continue enabled; approving queued G113 preview..."
        else
          statusText = "Submitting queued G113 preview decision..."
      }
      else if ( previewPending )
        statusText = "Queued G113 preview waiting for confirmation before execution."
      else
        statusText = "Last queued G113 path accepted."

      summaryText =
        "Lines " + firstLine + "-" + lastLine
        + " | " + preview.summary.g113Count + " G113"
        + " | " + preview.summary.segmentCount + " segments"
        + " | " + formatNumber( preview.summary.totalPathLength, 1 ) + " mm"

      if ( preview.stopAfterBlock )
        summaryText += " | single-step"
      if ( preview.useMaxSpeed )
        summaryText += " | max-speed default"

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
    $( "#queuedMotionPreviewContinueButton" ).prop( "disabled", ! previewPending || decisionPending )
    $( "#queuedMotionPreviewCancelButton" ).prop( "disabled", ! previewPending || decisionPending )
    $( "#queuedMotionPreviewAutoContinue" ).prop( "checked", autoContinue )
    $( "#queuedMotionPreviewUseMaxSpeed" )
      .prop( "checked", useMaxSpeed )
      .prop( "disabled", decisionPending || useMaxSpeedPending )

    setRows( "#queuedMotionPreviewSource", sourceRows, "No queued G113 lines are waiting." )
    setRows( "#queuedMotionPreviewSegments", segmentRows, "No queued segments are waiting." )
  }

  function loadAutoContinue()
  {
    try
    {
      autoContinue = "true" === window.localStorage.getItem( AUTO_CONTINUE_STORAGE_KEY )
    }
    catch ( error )
    {
      autoContinue = false
    }
  }

  function saveAutoContinue()
  {
    try
    {
      window.localStorage.setItem( AUTO_CONTINUE_STORAGE_KEY, autoContinue ? "true" : "false" )
    }
    catch ( error )
    {
      // Ignore storage failures and keep the setting in-memory for this session.
    }
  }

  function applyPreviewData(data)
  {
    if ( data !== null && data !== undefined )
    {
      preview = data
      previewPending = true
      decisionPending = false
      if ( preview.limits )
        limits = buildLimits( preview.limits )
      if ( preview.hasOwnProperty( "useMaxSpeed" ) )
        useMaxSpeed = true === preview.useMaxSpeed
      return
    }

    previewPending = false
    decisionPending = false
  }

  function measureCanvasWidth(canvasId)
  {
    var canvas = document.getElementById( canvasId )
    if ( ! canvas )
      return 0

    var width = $( canvas ).innerWidth()
    if ( ! width || width < 10 )
      width = 620
    return width
  }

  function refreshPreview()
  {
    uiServices.call(
      commands.process.getQueuedMotionPreview,
      {},
      function( data )
      {
        applyPreviewData( data )
        updateDetails()
        renderCanvas()
        maybeAutoContinue()
      }
    )
  }

  function loadUseMaxSpeed()
  {
    uiServices.call(
      commands.process.getQueuedMotionUseMaxSpeed,
      {},
      function( data )
      {
        useMaxSpeed = true === data
        updateDetails()
      }
    )
  }

  function setUseMaxSpeed(enabled)
  {
    useMaxSpeedPending = true
    updateDetails()

    uiServices.call(
      commands.process.setQueuedMotionUseMaxSpeed,
      { enabled: enabled },
      function( data )
      {
        useMaxSpeed = true === data
        useMaxSpeedPending = false
        updateDetails()
        refreshPreview()
      },
      function()
      {
        useMaxSpeedPending = false
        updateDetails()
      }
    )
  }

  function ensureCanvas(canvasId, height)
  {
    var canvas = document.getElementById( canvasId )
    if ( ! canvas )
      return null

    var width = $( canvas ).innerWidth()
    if ( ! width || width < 10 )
      width = 620

    var pixelRatio = window.devicePixelRatio || 1
    canvas.width = Math.round( width * pixelRatio )
    canvas.height = Math.round( height * pixelRatio )
    canvas.style.height = height + "px"

    var context = canvas.getContext( "2d" )
    context.setTransform( pixelRatio, 0, 0, pixelRatio, 0, 0 )
    context.clearRect( 0, 0, width, height )

    return {
      canvas: canvas,
      context: context,
      width: width,
      height: height
    }
  }

  function plotMetrics(bounds)
  {
    var xSpan = Math.max( 1, bounds.xRange.max - bounds.xRange.min )
    var ySpan = Math.max( 1, bounds.yRange.max - bounds.yRange.min )
    return {
      xSpan: xSpan,
      ySpan: ySpan
    }
  }

  function axisRange(minValue, maxValue, fallbackMin, fallbackMax)
  {
    if ( ! isFinite( minValue ) )
      minValue = fallbackMin
    if ( ! isFinite( maxValue ) )
      maxValue = fallbackMax
    if ( maxValue <= minValue )
      maxValue = minValue + Math.max( 1, fallbackMax - fallbackMin )
    return {
      min: minValue,
      max: maxValue
    }
  }

  function viewSpec(viewName, geometry)
  {
    var zRange = axisRange(
      geometry.zFront,
      geometry.zBack,
      0.0,
      400.0
    )

    if ( "xz" === viewName )
    {
      return {
        title: "XZ Plane",
        canvasId: "queuedMotionPreviewXZCanvas",
        xAxisLabel: "X",
        yAxisLabel: "Z",
        xRange: axisRange( geometry.limitLeft, geometry.limitRight, 0.0, 7360.0 ),
        yRange: zRange,
        pathColor: "#38bdf8",
        startColor: "#22d3ee",
        headColor: "#f8fafc",
        projected: true
      }
    }

    if ( "yz" === viewName )
    {
      return {
        title: "YZ Plane",
        canvasId: "queuedMotionPreviewYZCanvas",
        xAxisLabel: "Z",
        yAxisLabel: "Y",
        xRange: zRange,
        yRange: axisRange( geometry.limitBottom, geometry.limitTop, 0.0, 3000.0 ),
        reverseX: true,
        pathColor: "#a78bfa",
        startColor: "#c4b5fd",
        headColor: "#f8fafc",
        projected: true
      }
    }

    return {
      title: "XY Plane",
      canvasId: "queuedMotionPreviewXYCanvas",
      xAxisLabel: "X",
      yAxisLabel: "Y",
      xRange: axisRange( geometry.limitLeft, geometry.limitRight, 0.0, 7360.0 ),
      yRange: axisRange( geometry.limitBottom, geometry.limitTop, 0.0, 3000.0 ),
      pathColor: "#22d3ee",
      startColor: "#67e8f9",
      headColor: "#f8fafc",
      projected: false
    }
  }

  function pointToCanvas(point, bounds, layout)
  {
    var xSpan = Math.max( 1, bounds.xRange.max - bounds.xRange.min )
    var ySpan = Math.max( 1, bounds.yRange.max - bounds.yRange.min )
    var xRatio = ( point.x - bounds.xRange.min ) / xSpan
    var yRatio = ( point.y - bounds.yRange.min ) / ySpan

    if ( true === bounds.reverseX )
      xRatio = 1 - xRatio

    return {
      x: layout.plotLeft + ( xRatio * xSpan * layout.xScale ),
      y: layout.plotBottom - ( yRatio * ySpan * layout.yScale )
    }
  }

  function buildViewLayout(viewName, geometry, canvasWidth, xScale, yScale)
  {
    var spec = viewSpec( viewName, geometry )
    var metrics = plotMetrics( spec )
    var usableWidth = Math.max( 1, canvasWidth - ( 2 * PADDING ) )
    var plotWidth = metrics.xSpan * xScale
    var plotHeight = metrics.ySpan * yScale
    var height = Math.max(
      MIN_VIEW_HEIGHT,
      Math.ceil( plotHeight + ( 2 * PADDING ) + LEGEND_SPACE )
    )
    var plotLeft = PADDING + Math.max( 0, ( usableWidth - plotWidth ) / 2 )
    var plotBottom = height - PADDING - LEGEND_SPACE

    return {
      spec: spec,
      width: canvasWidth,
      height: height,
      xScale: xScale,
      yScale: yScale,
      plotLeft: plotLeft,
      plotBottom: plotBottom,
      plotWidth: plotWidth,
      plotHeight: plotHeight,
      usableWidth: usableWidth
    }
  }

  function buildViewLayouts(geometry)
  {
    var views = [ "xz", "xy", "yz" ]
    var layouts = {}
    var sharedScale = null

    for ( var index = 0; index < views.length; index += 1 )
    {
      var viewName = views[ index ]
      var spec = viewSpec( viewName, geometry )
      var width = measureCanvasWidth( spec.canvasId )
      var span = Math.max( 1, spec.xRange.max - spec.xRange.min )
      var usableWidth = Math.max( 1, width - ( 2 * PADDING ) )
      var candidate = ( usableWidth - 2 ) / span
      if ( ! isFinite( candidate ) || candidate <= 0 )
        candidate = 1
      if ( null === sharedScale || candidate < sharedScale )
        sharedScale = candidate
    }

    if ( null === sharedScale || ! isFinite( sharedScale ) || sharedScale <= 0 )
      sharedScale = 1

    for ( var layoutIndex = 0; layoutIndex < views.length; layoutIndex += 1 )
    {
      var layoutViewName = views[ layoutIndex ]
      var layoutSpec = viewSpec( layoutViewName, geometry )
      var layoutWidth = measureCanvasWidth( layoutSpec.canvasId )
      var xScale = sharedScale
      var yScale = sharedScale

      if ( "yz" === layoutViewName )
        xScale = sharedScale * YZ_Z_AXIS_SCALE_FACTOR

      layouts[ layoutViewName ] = buildViewLayout(
        layoutViewName,
        geometry,
        layoutWidth,
        xScale,
        yScale
      )
    }

    return layouts
  }

  function drawPanelFrame(context, bounds, layout)
  {
    context.save()
    context.strokeStyle = "rgba(148, 163, 184, 0.55)"
    context.lineWidth = 1
    context.strokeRect(
      PADDING,
      PADDING,
      layout.width - ( 2 * PADDING ),
      layout.height - ( 2 * PADDING )
    )
    context.restore()
  }

  function drawAxisGuide(context, bounds, layout)
  {
    context.save()
    context.fillStyle = "rgba(148, 163, 184, 0.9)"
    context.font = "11px Consolas"
    context.fillText( bounds.xAxisLabel + " ->", PADDING + 4, layout.height - 16 )
    context.fillText( bounds.yAxisLabel + " ^", PADDING + 4, layout.height - 5 )
    context.restore()
  }

  function currentHeadPosition()
  {
    if ( motorStatus && motorStatus.motor )
    {
      var x = parseFloat( motorStatus.motor[ "xPosition" ] )
      var y = parseFloat( motorStatus.motor[ "yPosition" ] )
      var z = parseFloat( motorStatus.motor[ "zPosition" ] )
      if ( isFinite( x ) && isFinite( y ) && isFinite( z ) )
        return { x: x, y: y, z: z }
    }

    if ( preview && preview.actualHead )
    {
      var fallbackZ = 0.0
      if ( motorStatus && motorStatus.motor )
      {
        fallbackZ = parseFloat( motorStatus.motor[ "zPosition" ] )
        if ( ! isFinite( fallbackZ ) )
          fallbackZ = 0.0
      }
      return {
        x: parseFloat( preview.actualHead.x ),
        y: parseFloat( preview.actualHead.y ),
        z: fallbackZ
      }
    }

    return null
  }

  function pinNumberFromName(name)
  {
    var text = String( name || "" )
    var digits = text.replace( /^[^0-9]+/, "" )
    var value = parseInt( digits, 10 )
    return isFinite( value ) ? value : 0
  }

  function buildCalibrationSides(calibration)
  {
    var sides = {
      F: [],
      B: []
    }

    if ( ! calibration || ! calibration.pins )
      return sides

    for ( var index = 0; index < calibration.pins.length; index += 1 )
    {
      var pin = calibration.pins[ index ]
      var name = String( pin.name || "" )
      var side = name.charAt( 0 )
      if ( ! sides.hasOwnProperty( side ) )
        continue
      sides[ side ].push( {
        name: name,
        number: pinNumberFromName( name ),
        x: parseFloat( pin.x ),
        y: parseFloat( pin.y ),
        z: parseFloat( pin.z )
      } )
    }

    for ( var sideKey in sides )
    {
      sides[ sideKey ].sort( function( a, b ) {
        if ( a.number !== b.number )
          return a.number - b.number
        return a.name.localeCompare( b.name )
      } )
    }

    return sides
  }

  function sampleSidePoints(points, count)
  {
    if ( ! points || 0 === points.length )
      return []

    if ( points.length <= count )
      return points.slice( 0 )

    var sampled = []
    var lastIndex = points.length - 1
    for ( var sampleIndex = 0; sampleIndex < count; sampleIndex += 1 )
    {
      var ratio = count <= 1 ? 0.0 : sampleIndex / ( count - 1 )
      var pointIndex = Math.round( ratio * lastIndex )
      if ( pointIndex < 0 )
        pointIndex = 0
      if ( pointIndex > lastIndex )
        pointIndex = lastIndex
      sampled.push( points[ pointIndex ] )
    }
    return sampled
  }

  function calibrationWireframeSegments()
  {
    if ( ! layerCalibration || ! layerCalibration.pins )
      return []

    var sides = buildCalibrationSides( layerCalibration )
    var front = sampleSidePoints( sides.F, 9 )
    var back = sampleSidePoints( sides.B, 9 )
    var segments = []
    var count = Math.min( front.length, back.length )

    if ( 0 === count )
      return segments

    for ( var index = 0; index < count; index += 1 )
    {
      var frontPoint = front[ index ]
      var backPoint = back[ index ]

      if ( index > 0 )
      {
        segments.push( {
          kind: "front",
          start: front[ index - 1 ],
          end: frontPoint
        } )
        segments.push( {
          kind: "back",
          start: back[ index - 1 ],
          end: backPoint
        } )
      }

      segments.push( {
        kind: "cross",
        start: frontPoint,
        end: backPoint
      } )
    }

    return segments
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

  function segmentSourcePoints(segment)
  {
    var points = [ segment.start ]

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
          points.push(
            {
              x: center.x + radius * Math.cos( angle ),
              y: center.y + radius * Math.sin( angle )
            }
          )
        }
        return points
      }
    }

    points.push( segment.end )
    return points
  }

  function projectPoint(point, viewName, headPosition)
  {
    if ( "xz" === viewName )
      return { x: point.x, y: headPosition.z }

    if ( "yz" === viewName )
      return { x: headPosition.z, y: point.y }

    return { x: point.x, y: point.y }
  }

  function projectCalibrationPoint(point, viewName)
  {
    if ( "xz" === viewName )
      return { x: point.x, y: point.z }

    if ( "yz" === viewName )
      return { x: point.z, y: point.y }

    return { x: point.x, y: point.y }
  }

  function drawCalibrationWireframe(context, viewName, bounds, layout)
  {
    var segments = calibrationWireframeSegments()
    if ( 0 === segments.length )
      return

    context.save()
    context.lineWidth = 1.4
    context.setLineDash( [])

    for ( var index = 0; index < segments.length; index += 1 )
    {
      var segment = segments[ index ]
      var start = pointToCanvas(
        projectCalibrationPoint( segment.start, viewName ),
        bounds,
        layout
      )
      var end = pointToCanvas(
        projectCalibrationPoint( segment.end, viewName ),
        bounds,
        layout
      )

      if ( "cross" === segment.kind )
      {
        context.strokeStyle = "rgba(148, 163, 184, 0.5)"
        context.setLineDash( [ 4, 4 ] )
      }
      else if ( "front" === segment.kind )
      {
        context.strokeStyle = "rgba(34, 197, 94, 0.55)"
      }
      else
      {
        context.strokeStyle = "rgba(59, 130, 246, 0.55)"
      }

      context.beginPath()
      context.moveTo( start.x, start.y )
      context.lineTo( end.x, end.y )
      context.stroke()
    }

    context.restore()
  }

  function drawPath(context, viewName, bounds, layout)
  {
    if ( ! preview || ! preview.segments || 0 === preview.segments.length )
      return

    var head = currentHeadPosition()
    if ( ! head )
      return

    var firstPoint = projectPoint( preview.start, viewName, head )
    var start = pointToCanvas( firstPoint, bounds, layout )
    context.save()
    context.strokeStyle = bounds.startColor
    context.lineWidth = viewName === "xy" ? 3 : 2.5
    if ( viewName !== "xy" )
      context.setLineDash( [ 7, 5 ] )
    context.beginPath()
    context.arc( start.x, start.y, 8, 0, 2 * Math.PI )
    context.stroke()
    context.restore()

    for ( var index = 0; index < preview.segments.length; index += 1 )
    {
      var segment = preview.segments[ index ]
      var sourcePoints = segmentSourcePoints( segment )
      var projectedPoint = pointToCanvas(
        projectPoint( sourcePoints[ 0 ], viewName, head ),
        bounds,
        layout
      )

      context.save()
      context.strokeStyle = segment.kind === "circle"
        ? bounds.pathColor
        : ( viewName === "xy" ? "#f59e0b" : bounds.pathColor )
      context.lineWidth = viewName === "xy" ? 3 : 2.25
      if ( viewName !== "xy" )
        context.setLineDash( [ 7, 5 ] )
      context.beginPath()
      context.moveTo( projectedPoint.x, projectedPoint.y )

      for ( var pointIndex = 1; pointIndex < sourcePoints.length; pointIndex += 1 )
      {
        var mapped = pointToCanvas(
          projectPoint( sourcePoints[ pointIndex ], viewName, head ),
          bounds,
          layout
        )
        context.lineTo( mapped.x, mapped.y )
      }

      context.stroke()
      context.fillStyle = context.strokeStyle
      context.beginPath()
      context.arc(
        projectedPoint.x,
        projectedPoint.y,
        viewName === "xy" ? 3.5 : 3,
        0,
        2 * Math.PI
      )
      context.fill()

      var finalPoint = pointToCanvas(
        projectPoint( sourcePoints[ sourcePoints.length - 1 ], viewName, head ),
        bounds,
        layout
      )
      context.font = "11px Consolas"
      context.fillText( String( segment.index ), finalPoint.x + 5, finalPoint.y - 5 )
      context.restore()
    }
  }

  function drawCurrentHead(context, viewName, bounds, layout)
  {
    var head = currentHeadPosition()
    if ( ! head )
      return

    var position = pointToCanvas( projectPoint( head, viewName, head ), bounds, layout )
    context.save()
    context.fillStyle = bounds.headColor
    context.strokeStyle = "#0f172a"
    context.lineWidth = 2
    context.beginPath()
    context.arc( position.x, position.y, 7, 0, 2 * Math.PI )
    context.fill()
    context.stroke()
    context.fillStyle = "rgba(248, 250, 252, 0.9)"
    context.font = "12px Consolas"
    context.fillText( "HEAD", position.x + 10, position.y - 10 )
    if ( "xy" !== viewName )
      context.fillText( "Z " + formatNumber( head.z, 1 ), position.x + 10, position.y + 14 )
    context.restore()
  }

  function renderCanvas()
  {
    var geometry = activeLimits()
    var layouts = buildViewLayouts( geometry )
    renderViewWithLayouts( "xz", layouts )
    renderViewWithLayouts( "xy", layouts )
    renderViewWithLayouts( "yz", layouts )
  }

  function renderViewWithLayouts(viewName, layouts)
  {
    var layout = layouts[ viewName ]
    if ( ! layout )
      return

    var spec = layout.spec
    var canvasState = ensureCanvas( spec.canvasId, layout.height )
    if ( ! canvasState )
      return

    drawPanelFrame( canvasState.context, spec, layout )
    drawAxisGuide( canvasState.context, spec, layout )
    drawCalibrationWireframe(
      canvasState.context,
      viewName,
      spec,
      layout
    )
    drawPath( canvasState.context, viewName, spec, layout )
    drawCurrentHead( canvasState.context, viewName, spec, layout )
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

  function maybeAutoContinue()
  {
    if ( autoContinue && previewPending && ! decisionPending )
      submitDecision( commands.process.continueQueuedMotionPreview )
  }

  function loadLayerCalibration()
  {
    uiServices.call(
      commands.process.getLayerCalibration,
      {},
      function( data )
      {
        layerCalibration = data || null
        renderCanvas()
      },
      function()
      {
        layerCalibration = null
        renderCanvas()
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

    $( "#queuedMotionPreviewAutoContinue" )
      .off( "change.queuedPreview" )
      .on( "change.queuedPreview", function() {
        autoContinue = $( this ).is( ":checked" )
        saveAutoContinue()
        updateDetails()
        maybeAutoContinue()
      } )

    $( "#queuedMotionPreviewUseMaxSpeed" )
      .off( "change.queuedPreview" )
      .on( "change.queuedPreview", function() {
        var enabled = $( this ).is( ":checked" )
        if ( enabled === useMaxSpeed || useMaxSpeedPending )
        {
          updateDetails()
          return
        }
        setUseMaxSpeed( enabled )
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
      commands = uiServices.getCommands()
      limits = buildLimits( {} )
      loadAutoContinue()

      bindControls()
      updateDetails()
      loadGeometry()
      loadLayerCalibration()
      loadUseMaxSpeed()

      winder.addPeriodicCallback(
        commands.process.getQueuedMotionPreview,
        function( data )
        {
          applyPreviewData( data )
          updateDetails()
          renderCanvas()
          maybeAutoContinue()
        }
      )

      winder.addPeriodicEndCallback( renderCanvas )

      $( window ).off( "resize.queuedPreview" ).on( "resize.queuedPreview", renderCanvas )
    }
  )
}
