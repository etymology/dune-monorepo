///////////////////////////////////////////////////////////////////////////////
// Name: LoadcellCalibrate.js
// Uses: Load-cell calibration page. Capture (weight, tension_tag) samples, fit a
//   quartic (tension_tag -> tension in newtons), plot the current PLC fit, the
//   samples, and the new fit, and write the new coefficients to the PLC.
//   Samples can be selected in or out of the fit; selected ones draw red and
//   excluded ones grey. Selecting nothing fits every sample.
///////////////////////////////////////////////////////////////////////////////

function LoadcellCalibrate(modules) {
  var uiServices = null
  var commands = null
  try {
    uiServices = modules.get("UiServices")
    commands = uiServices.getCommands()
  } catch (e) {
    console.error("Failed to initialize LoadcellCalibrate: " + e.message)
    return
  }

  var cmd = (commands && commands.loadcellCalibration) || {}
  var COEF_KEYS = ["a0", "a1", "a2", "a3", "a4"]

  var state = null
  var live = { tensionTag: null, tension: null }
  var liveTimer = null

  // --- helpers -------------------------------------------------------------
  function name(value, fallback) {
    return value || fallback
  }

  function isNum(value) {
    return typeof value === "number" && isFinite(value)
  }

  function fmt(value, decimals) {
    if (!isNum(value)) return "-"
    return value.toFixed(decimals === undefined ? 3 : decimals)
  }

  function fmtCoef(value) {
    if (!isNum(value)) return "-"
    if (value === 0) return "0"
    return Number(value.toPrecision(6)).toString()
  }

  function evalQuartic(coef, x) {
    if (!coef) return null
    var a = []
    for (var i = 0; i < COEF_KEYS.length; i += 1) {
      var v = coef[COEF_KEYS[i]]
      if (!isNum(v)) return null
      a.push(v)
    }
    return a[0] + a[1] * x + a[2] * x * x + a[3] * x * x * x + a[4] * x * x * x * x
  }

  function clearStatus() {
    $("#loadcellCalibrateMessage").addClass("hidden").text("")
    $("#loadcellCalibrateError").addClass("hidden").text("")
  }

  function showMessage(text) {
    $("#loadcellCalibrateMessage").text(text || "").removeClass("hidden")
  }

  function showError(text) {
    $("#loadcellCalibrateError")
      .text("Error: " + (text || "Command failed."))
      .removeClass("hidden")
  }

  function responseError(response) {
    if (response && response.error && response.error.message) {
      return response.error.message
    }
    return "Command failed."
  }

  // --- data ----------------------------------------------------------------
  var DEGREE_NAMES = { 1: "Linear", 2: "Quadratic", 3: "Cubic", 4: "Quartic" }

  function applyState(data) {
    state = data
    if (data && data.live) live = data.live
    if (data && data.fixIntercept !== undefined) {
      $("#loadcellFixIntercept").prop("checked", !!data.fixIntercept)
    }
    if (data && data.maxDegree !== undefined) {
      $("#loadcellMaxDegree").val(String(data.maxDegree))
    }
    render()
  }

  function loadState() {
    uiServices.call(
      name(cmd.getState, "loadcell_calibration.get_state"),
      {},
      function(data) {
        applyState(data)
      },
      function(response) {
        showError(responseError(response))
      }
    )
  }

  function pollLive() {
    uiServices.call(
      name(cmd.readLive, "loadcell_calibration.read_live"),
      {},
      function(data) {
        if (data) {
          live = data
          renderLive()
          drawPlot()
        }
      },
      function() {
        /* keep last values on transient errors */
      }
    )
  }

  // --- rendering -----------------------------------------------------------
  function renderLive() {
    $("#loadcellLiveTensionTag").text(fmt(live.tensionTag, 4))
    $("#loadcellLiveTension").text(fmt(live.tension, 3))
  }

  // A sample drives the fit when it is selected, or when nothing is selected
  // at all (the backend falls back to every sample in that case).
  function usedInFit(sample) {
    return sample.usedInFit !== false
  }

  function selectedCount() {
    if (state && isNum(state.selectedCount)) return state.selectedCount
    var samples = (state && state.samples) || []
    var count = 0
    samples.forEach(function(s) {
      if (s.selected) count += 1
    })
    return count
  }

  function renderSamples() {
    var samples = (state && state.samples) || []
    if (samples.length === 0) {
      $("#loadcellSampleCount").text("No samples recorded.")
      $("#loadcellSamplesTable").addClass("hidden")
      $("#loadcellSamplesBody").empty()
      $("#loadcellClearSelectionButton").prop("disabled", true)
      return
    }
    var chosen = selectedCount()
    $("#loadcellSampleCount").text(
      samples.length + " sample" + (samples.length === 1 ? "" : "s") + " recorded. " +
        (chosen === 0
          ? "None selected — fitting all of them."
          : "Fitting the " + chosen + " selected.")
    )
    $("#loadcellClearSelectionButton").prop("disabled", chosen === 0)

    var rows = ""
    samples.forEach(function(sample) {
      var rowClass = usedInFit(sample)
        ? "loadcellSampleUsed"
        : "loadcellSampleExcluded"
      rows +=
        '<tr class="' + rowClass + '">' +
        '<td class="loadcellSelectCell"><input type="checkbox" class="loadcellSelectSample" data-id="' +
        sample.id +
        '"' + (sample.selected ? " checked" : "") + " /></td>" +
        "<td>" + sample.id + "</td>" +
        "<td>" + fmt(sample.grams, 1) + "</td>" +
        "<td>" + fmt(sample.newtons, 3) + "</td>" +
        "<td>" + fmt(sample.tensionTag, 4) + "</td>" +
        '<td><button type="button" class="loadcellMiniButton loadcellDeleteSample" data-id="' +
        sample.id +
        '">Delete</button></td>' +
        "</tr>"
    })
    $("#loadcellSamplesBody").html(rows)
    $("#loadcellSamplesTable").removeClass("hidden")
  }

  function renderFit() {
    var plc = (state && state.plc) || { coefficients: {} }
    var fit = state && state.fit
    var fitCoef = fit && !fit.error ? fit.coefficients : null

    var rows = ""
    COEF_KEYS.forEach(function(key) {
      rows +=
        "<tr>" +
        "<td>" + key + "</td>" +
        "<td>" + fmtCoef(plc.coefficients ? plc.coefficients[key] : null) + "</td>" +
        "<td>" + (fitCoef ? fmtCoef(fitCoef[key]) : "-") + "</td>" +
        "</tr>"
    })
    $("#loadcellFitBody").html(rows)

    var stats
    var canApply = false
    if (!fit) {
      stats = "Need at least 2 samples to fit. Add more to allow a higher degree."
    } else if (fit.error) {
      stats = fit.error
    } else {
      var degreeName = DEGREE_NAMES[fit.degree] || ("Degree " + fit.degree)
      var capped = fit.degree < fit.maxDegree ? " (limited by sample count)" : ""
      stats =
        degreeName + " fit on " + fit.pointCount + " points" + capped +
        " | RMS residual " + fmt(fit.rmsNewtons, 4) +
        " N | max residual " + fmt(fit.maxResidualNewtons, 4) + " N"
      canApply = true
    }
    $("#loadcellFitStats").text(stats)
    $("#loadcellApplyButton").prop("disabled", !canApply)
  }

  function render() {
    renderLive()
    renderSamples()
    renderFit()
    drawPlot()
  }

  // --- plot ----------------------------------------------------------------
  function drawPlot() {
    var canvas = document.getElementById("loadcellPlot")
    if (!canvas || !canvas.getContext) return
    var ctx = canvas.getContext("2d")

    // Render into a high-resolution backing store sized to the displayed box,
    // so the plot stays crisp on HiDPI screens. Drawing uses CSS-pixel coords.
    var rect = canvas.getBoundingClientRect()
    var W = Math.round(rect.width) || 760
    var H = Math.round(W * 0.72)
    canvas.style.height = H + "px"
    var scale = (window.devicePixelRatio || 1) * 2
    canvas.width = Math.round(W * scale)
    canvas.height = Math.round(H * scale)
    ctx.setTransform(scale, 0, 0, scale, 0, 0)
    ctx.clearRect(0, 0, W, H)

    var margin = { left: 56, right: 18, top: 18, bottom: 44 }
    var plotW = W - margin.left - margin.right
    var plotH = H - margin.top - margin.bottom

    var samples = (state && state.samples) || []
    // Draw the PLC curve whenever the coefficients are all finite (evalQuartic
    // returns null otherwise), independent of the live-read availability flag.
    var plcCoef = state && state.plc ? state.plc.coefficients : null
    var newCoef =
      state && state.fit && !state.fit.error ? state.fit.coefficients : null

    // Both axes default to 0..12 and only grow to fit the data.
    var xMin = 0
    var xMax = 12
    var yMin = 0
    var yMax = 12
    samples.forEach(function(s) {
      if (isNum(s.tensionTag)) xMax = Math.max(xMax, s.tensionTag * 1.05)
      if (isNum(s.newtons)) {
        yMax = Math.max(yMax, s.newtons * 1.05)
        yMin = Math.min(yMin, s.newtons)
      }
    })
    if (isNum(live.tensionTag)) xMax = Math.max(xMax, live.tensionTag * 1.05)

    // Sample the fit curves across the x-range. The y-range intentionally
    // ignores curve values so a steep quartic tail does not squash the data;
    // curves are clipped to the plot area instead.
    var curvePoints = 220
    var curves = []
    function buildCurve(coef, color) {
      if (!coef) return
      var pts = []
      for (var i = 0; i <= curvePoints; i += 1) {
        var x = xMin + ((xMax - xMin) * i) / curvePoints
        var y = evalQuartic(coef, x)
        if (y !== null) pts.push([x, y])
      }
      if (pts.length) curves.push({ pts: pts, color: color })
    }
    buildCurve(plcCoef, "#888")
    buildCurve(newCoef, "#2d6cdf")

    function sx(x) {
      return margin.left + ((x - xMin) / (xMax - xMin)) * plotW
    }
    function sy(y) {
      return margin.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH
    }

    // Grid + tick labels.
    ctx.lineWidth = 1
    ctx.fillStyle = "#555"
    ctx.font = "12px sans-serif"
    var ticks = 6
    ctx.textAlign = "right"
    ctx.textBaseline = "middle"
    for (var iy = 0; iy <= ticks; iy += 1) {
      var yVal = yMin + ((yMax - yMin) * iy) / ticks
      var py = sy(yVal)
      ctx.strokeStyle = "#eee"
      ctx.beginPath()
      ctx.moveTo(margin.left, py)
      ctx.lineTo(margin.left + plotW, py)
      ctx.stroke()
      ctx.fillText(yVal.toFixed(1), margin.left - 6, py)
    }
    ctx.textAlign = "center"
    ctx.textBaseline = "top"
    for (var ix = 0; ix <= ticks; ix += 1) {
      var xVal = xMin + ((xMax - xMin) * ix) / ticks
      var px = sx(xVal)
      ctx.strokeStyle = "#eee"
      ctx.beginPath()
      ctx.moveTo(px, margin.top)
      ctx.lineTo(px, margin.top + plotH)
      ctx.stroke()
      ctx.fillText(xVal.toFixed(1), px, margin.top + plotH + 6)
    }

    // Axis frame.
    ctx.strokeStyle = "#999"
    ctx.strokeRect(margin.left, margin.top, plotW, plotH)

    // Axis labels.
    ctx.fillStyle = "#333"
    ctx.font = "13px sans-serif"
    ctx.textAlign = "center"
    ctx.textBaseline = "bottom"
    ctx.fillText("tension_tag", margin.left + plotW / 2, H - 4)
    ctx.save()
    ctx.translate(13, margin.top + plotH / 2)
    ctx.rotate(-Math.PI / 2)
    ctx.textBaseline = "top"
    ctx.fillText("tension (N)", 0, 0)
    ctx.restore()

    // Everything data-driven is clipped to the plot rectangle.
    ctx.save()
    ctx.beginPath()
    ctx.rect(margin.left, margin.top, plotW, plotH)
    ctx.clip()

    // Live tension_tag marker.
    if (isNum(live.tensionTag) && live.tensionTag >= xMin && live.tensionTag <= xMax) {
      ctx.strokeStyle = "#d08a00"
      ctx.setLineDash([5, 4])
      ctx.beginPath()
      ctx.moveTo(sx(live.tensionTag), margin.top)
      ctx.lineTo(sx(live.tensionTag), margin.top + plotH)
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Fit curves.
    ctx.lineWidth = 2
    curves.forEach(function(c) {
      ctx.strokeStyle = c.color
      ctx.beginPath()
      c.pts.forEach(function(p, i) {
        var X = sx(p[0])
        var Y = sy(p[1])
        if (i === 0) ctx.moveTo(X, Y)
        else ctx.lineTo(X, Y)
      })
      ctx.stroke()
    })

    // Sample points: red for the ones the fit uses, grey for the excluded.
    // Excluded first so the fitted points stay on top where they overlap.
    function drawSamples(used, color) {
      ctx.fillStyle = color
      samples.forEach(function(s) {
        if (!isNum(s.tensionTag) || !isNum(s.newtons)) return
        if (usedInFit(s) !== used) return
        ctx.beginPath()
        ctx.arc(sx(s.tensionTag), sy(s.newtons), 4.5, 0, Math.PI * 2)
        ctx.fill()
      })
    }
    drawSamples(false, "#9aa0a6")
    drawSamples(true, "#e5484d")

    ctx.restore()
  }

  // --- actions -------------------------------------------------------------
  function mutate(command, args, successMessage) {
    clearStatus()
    uiServices.call(
      command,
      args || {},
      function(data) {
        if (successMessage) showMessage(successMessage)
        applyState(data)
      },
      function(response) {
        showError(responseError(response))
      }
    )
  }

  $("#loadcellCaptureButton").off("click").on("click", function() {
    var grams = parseFloat($("#loadcellGrams").val())
    if (!isNum(grams)) {
      showError("Enter the hung weight in grams first.")
      return
    }
    clearStatus()
    var button = $(this)
    button.prop("disabled", true).text("Capturing…")
    uiServices.call(
      name(cmd.captureSample, "loadcell_calibration.capture_sample"),
      { grams: grams },
      function(data) {
        button.prop("disabled", false).text("Capture sample (auto-settle)")
        var cap = data && data.capture
        if (cap && !cap.settled) {
          showMessage(
            "Captured (did not fully settle: spread " + fmt(cap.spread, 4) +
              "). Consider re-capturing."
          )
        } else if (cap) {
          showMessage(
            "Captured tension_tag " + fmt(cap.tensionTag, 4) +
              " for " + grams + " g."
          )
        }
        applyState(data)
      },
      function(response) {
        button.prop("disabled", false).text("Capture sample (auto-settle)")
        showError(responseError(response))
      }
    )
  })

  $("#loadcellAddManualButton").off("click").on("click", function() {
    var grams = parseFloat($("#loadcellGrams").val())
    var tag = parseFloat($("#loadcellManualTag").val())
    if (!isNum(grams) || !isNum(tag)) {
      showError("Enter both a weight (grams) and a manual tension_tag value.")
      return
    }
    mutate(
      name(cmd.addSample, "loadcell_calibration.add_sample"),
      { grams: grams, tension_tag: tag },
      "Added manual sample."
    )
    $("#loadcellManualTag").val("")
  })

  $("#loadcellClearButton").off("click").on("click", function() {
    if (!window.confirm("Delete all calibration samples?")) return
    mutate(
      name(cmd.clearSamples, "loadcell_calibration.clear_samples"),
      {},
      "Cleared all samples."
    )
  })

  $("#loadcellClearSelectionButton").off("click").on("click", function() {
    mutate(
      name(cmd.clearSelection, "loadcell_calibration.clear_selection"),
      {},
      "Cleared the selection; fitting all samples."
    )
  })

  $("#loadcellFixIntercept").off("change").on("change", function() {
    mutate(
      name(cmd.setFixIntercept, "loadcell_calibration.set_fix_intercept"),
      { enabled: $(this).prop("checked") },
      null
    )
  })

  $("#loadcellMaxDegree").off("change").on("change", function() {
    mutate(
      name(cmd.setMaxDegree, "loadcell_calibration.set_max_degree"),
      { max_degree: parseInt($(this).val(), 10) },
      null
    )
  })

  $("#loadcellApplyButton").off("click").on("click", function() {
    if (!window.confirm("Write the new a0..a4 coefficients to the PLC?")) return
    mutate(
      name(cmd.apply, "loadcell_calibration.apply"),
      {},
      "Applied new fit to the PLC."
    )
  })

  $(document)
    .off("click.loadcell")
    .off("change.loadcell")
    .on("click.loadcell", ".loadcellDeleteSample", function() {
      mutate(
        name(cmd.deleteSample, "loadcell_calibration.delete_sample"),
        { id: $(this).data("id") },
        null
      )
    })
    .on("change.loadcell", ".loadcellSelectSample", function() {
      mutate(
        name(cmd.setSampleSelected, "loadcell_calibration.set_sample_selected"),
        { id: $(this).data("id"), selected: $(this).prop("checked") },
        null
      )
    })

  // --- lifecycle -----------------------------------------------------------
  loadState()
  liveTimer = window.setInterval(pollLive, 500)

  modules.registerShutdownCallback(function() {
    if (liveTimer) {
      window.clearInterval(liveTimer)
      liveTimer = null
    }
    $(document).off("click.loadcell").off("change.loadcell")
  })
}
