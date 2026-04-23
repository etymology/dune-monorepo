function MachineGeometryCalibrate(modules) {
  var uiServices = null
  var commands = null
  try {
    uiServices = modules.get("UiServices")
    commands = uiServices.getCommands()
  } catch (e) {
    console.error("Failed to initialize MachineGeometryCalibrate: " + e.message)
    return
  }

  var currentState = null
  var activeOperation = null
  var progressPollTimer = null
  var activityEntries = []
  var lastMachineSolveStatusKey = null

  function commandName(path, fallback) {
    return path || fallback
  }

  function clearStatus() {
    $("#machineGeometryMessage").addClass("hidden").text("")
    $("#machineGeometryError").addClass("hidden").text("")
  }

  function showMessage(text) {
    $("#machineGeometryMessage").text(text || "").removeClass("hidden")
    appendActivity("info", text || "")
  }

  function showError(text) {
    var message = text || "Command failed."
    $("#machineGeometryError").text("Error: " + message).removeClass("hidden")
    appendActivity("error", message)
  }

  function timestamp() {
    var now = new Date()
    return now.toLocaleTimeString()
  }

  function appendActivity(level, text) {
    if (!text) return
    var entry = timestamp() + " [" + level + "] " + text
    activityEntries.push(entry)
    if (activityEntries.length > 12) {
      activityEntries = activityEntries.slice(activityEntries.length - 12)
    }
    $("#machineGeometryActivity").removeClass("hidden")
    $("#machineGeometryActivityLog").text(activityEntries.join("\n"))
    if (level === "error") {
      console.error("MachineGeometryCalibrate: " + text)
    } else {
      console.log("MachineGeometryCalibrate: " + text)
    }
  }

  function setActivityStatus(text) {
    if (!text) return
    $("#machineGeometryActivity").removeClass("hidden")
    $("#machineGeometryActivityStatus").text(text)
  }

  function formatDuration(seconds) {
    if (!$.isNumeric(seconds)) return null
    var totalSeconds = Math.max(0, Math.round(Number(seconds)))
    var minutes = Math.floor(totalSeconds / 60)
    var remainingSeconds = totalSeconds % 60
    if (minutes <= 0) return remainingSeconds + "s"
    return minutes + "m " + (remainingSeconds < 10 ? "0" : "") + remainingSeconds + "s"
  }

  function setActivityProgress(status) {
    var hasProgress =
      status
      && (
        $.isNumeric(status.percentComplete)
        || $.isNumeric(status.completedEvaluations)
        || $.isNumeric(status.totalEvaluations)
      )
    if (!hasProgress) {
      $("#machineGeometryActivityProgress").addClass("hidden")
      $("#machineGeometryActivityProgressLabel").text("0%")
      $("#machineGeometryActivityProgressMeta").text("0 / 0")
      $("#machineGeometryActivityProgressBar").css("width", "0%")
      $("#machineGeometryActivityProgressDetail").text("")
      return
    }

    var percent = $.isNumeric(status.percentComplete) ? Number(status.percentComplete) : 0
    percent = Math.max(0, Math.min(100, percent))
    var completed = $.isNumeric(status.completedEvaluations)
      ? Math.max(0, Math.floor(Number(status.completedEvaluations)))
      : 0
    var total = $.isNumeric(status.totalEvaluations)
      ? Math.max(completed, Math.floor(Number(status.totalEvaluations)))
      : completed

    var phaseLabels = {
      planning: "Planning",
      camera_coarse_x: "Camera X coarse",
      camera_coarse_y: "Camera Y coarse",
      camera_refine_x: "Camera X refine",
      camera_refine_y: "Camera Y refine",
      starting: "Starting",
      done: "Done"
    }
    var details = []
    if (status.phase) {
      var phaseLabel = phaseLabels[status.phase] || status.phase.replace(/^roller_(\d+)$/, "Roller $1")
      details.push("Phase " + phaseLabel)
    }
    if ($.isNumeric(status.levelIndex) && $.isNumeric(status.levelCount)) {
      details.push("Level " + status.levelIndex + " / " + status.levelCount)
    }
    if ($.isNumeric(status.stepSize)) {
      details.push("Step " + formatCompactNumber(status.stepSize, 3) + " mm")
    }
    if (status.candidateLabel) {
      details.push("Candidate " + status.candidateLabel)
    }
    var etaText = formatDuration(status.estimatedSecondsRemaining)
    if (etaText) {
      details.push("ETA " + etaText)
    }

    $("#machineGeometryActivity").removeClass("hidden")
    $("#machineGeometryActivityProgress").removeClass("hidden")
    $("#machineGeometryActivityProgressLabel").text(formatCompactNumber(percent, 1) + "%")
    $("#machineGeometryActivityProgressMeta").text(completed + " / " + total)
    $("#machineGeometryActivityProgressBar").css("width", percent + "%")
    $("#machineGeometryActivityProgressDetail").text(details.join(" | "))
  }

  function responseErrorMessage(response) {
    if (response && response.error && response.error.message) {
      return response.error.message
    }
    return "Command failed."
  }

  function machineSolveInProgress(status) {
    if (!status || !status.status) return false
    return (
      status.status === "running"
      || status.status === "cancel_requested"
      || status.status === "kill_requested"
    )
  }

  function stopProgressPoll() {
    if (progressPollTimer) {
      window.clearInterval(progressPollTimer)
      progressPollTimer = null
    }
    activeOperation = null
  }

  function renderMachineSolveStatus(status) {
    if (!status) return
    var statusKey = [
      status.operationId || "",
      status.status || "",
      status.step || "",
      status.message || "",
      status.updatedAt || "",
      status.completedEvaluations || "",
      status.totalEvaluations || "",
      status.percentComplete || "",
      status.phase || "",
      status.levelIndex || "",
      status.levelCount || "",
      status.stepSize || "",
      status.candidateLabel || ""
    ].join("|")
    if (statusKey === lastMachineSolveStatusKey) return
    lastMachineSolveStatusKey = statusKey

    var label = "Machine XY solve " + (status.status || "status")
    if ($.isNumeric(status.percentComplete)) {
      label += " (" + formatCompactNumber(status.percentComplete, 1) + "%)"
    }
    if (status.message) {
      label += ": " + status.message
    }
    setActivityStatus(label)
    setActivityProgress(status)
    appendActivity(status.status === "failed" ? "error" : "info", label)
  }

  function formatNumber(value, decimals) {
    if (!$.isNumeric(value)) return "-"
    var multiplier = Math.pow(10, decimals)
    value = Math.round(value * multiplier) / multiplier
    return value.toFixed(decimals)
  }

  function formatCompactNumber(value, decimals) {
    if (!$.isNumeric(value)) return "-"
    var multiplier = Math.pow(10, decimals)
    value = Math.round(value * multiplier) / multiplier
    return ("" + value).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1")
  }

  function rollerLabel(index) {
    return ["Left / Lower", "Left / Upper", "Right / Lower", "Right / Upper"][index] || ("Roller " + index)
  }

  function planeText(calibration) {
    if (!calibration || !calibration.coefficients || calibration.coefficients.length !== 3) return "-"
    return (
      "z = "
      + formatCompactNumber(calibration.coefficients[0], 6)
      + "x + "
      + formatCompactNumber(calibration.coefficients[1], 6)
      + "y + "
      + formatCompactNumber(calibration.coefficients[2], 6)
    )
  }

  function planeStatus(calibration, stale) {
    if (!calibration) return "No fit"
    if (calibration.fit_error) return calibration.fit_error
    if (!calibration.coefficients || calibration.coefficients.length !== 3) return "Waiting for a valid fit"
    var parts = []
    if ($.isNumeric(calibration.rank)) parts.push("rank " + calibration.rank)
    if ($.isNumeric(calibration.residual_sum_squares)) {
      parts.push("rss " + formatCompactNumber(calibration.residual_sum_squares, 4))
    }
    if (stale) parts.push("stale")
    return parts.join(" | ") || "Fit valid"
  }

  function measurementUseText(item) {
    var uses = []
    if (item.usableForMachineXY) uses.push("XY")
    if (item.usableForLayerZ) uses.push("Z")
    return uses.length > 0 ? uses.join(" + ") : "-"
  }

  function loadState(keepMessage) {
    uiServices.call(
      commandName(commands.process.machineGeometryGetState, "process.machine_geometry.get_state"),
      {},
      function(data) {
        if (!keepMessage) clearStatus()
        currentState = data
        render()
      },
      function(response) {
        showError(responseErrorMessage(response))
      }
    )
  }

  function callAndRefresh(command, args, successMessage, keepMessage) {
    appendActivity("info", "Calling " + command + ".")
    uiServices.call(
      command,
      args || {},
      function() {
        if (successMessage) showMessage(successMessage)
        loadState(keepMessage !== false)
      },
      function(response) {
        showError(responseErrorMessage(response))
        loadState(true)
      }
    )
  }

  function beginMachineXYSolve() {
    var command = commandName(
      commands.process.machineGeometrySolveMachineXY,
      "process.machine_geometry.solve_machine_xy"
    )
    var layer = activeLayer()
    activeOperation = "machine_xy"
    clearStatus()
    setActivityStatus("Machine XY solve: starting.")
    setActivityProgress({
      percentComplete: 0,
      completedEvaluations: 0,
      totalEvaluations: 0,
      phase: "starting"
    })
    appendActivity("info", "Starting Machine XY solve for layer " + (layer || "-") + ".")
    $("#machineGeometrySolveMachineXY").prop("disabled", true)
    $("#machineGeometryCancelMachineXY").prop("disabled", false)
    $("#machineGeometryKillMachineXY").prop("disabled", false)
    $("#machineGeometryApplyMachineXY").prop("disabled", true)

    if (progressPollTimer) {
      window.clearInterval(progressPollTimer)
    }
    progressPollTimer = window.setInterval(function() {
      loadState(true)
    }, 1000)

    uiServices.call(
      command,
      { layer: layer },
      function(data) {
        stopProgressPoll()
        if (data && data.killed) {
          showMessage("Killed Machine XY solve.")
        } else if (data && data.canceled) {
          showMessage("Canceled Machine XY solve.")
        } else if (data && data.fitError) {
          showError(data.fitError)
        } else {
          showMessage("Solved machine XY draft.")
        }
        loadState(true)
      },
      function(response) {
        stopProgressPoll()
        showError(responseErrorMessage(response))
        loadState(true)
      }
    )
  }

  function killMachineXYSolve() {
    var command = commandName(
      commands.process.machineGeometryKillMachineXY,
      "process.machine_geometry.kill_machine_xy"
    )
    var layer = activeLayer()
    appendActivity("info", "Requesting hard kill for Machine XY solve.")
    $("#machineGeometryKillMachineXY").prop("disabled", true)
    uiServices.call(
      command,
      { layer: layer },
      function(data) {
        if (data && data.killed) {
          setActivityStatus("Machine XY solve kill requested.")
          appendActivity("info", data.message || "Kill requested.")
        } else {
          appendActivity("info", (data && data.message) || "No active Machine XY solve to kill.")
        }
        loadState(true)
      },
      function(response) {
        showError(responseErrorMessage(response))
        loadState(true)
      }
    )
  }

  function cancelMachineXYSolve() {
    var command = commandName(
      commands.process.machineGeometryCancelMachineXY,
      "process.machine_geometry.cancel_machine_xy"
    )
    var layer = activeLayer()
    appendActivity("info", "Requesting cancel for Machine XY solve.")
    $("#machineGeometryCancelMachineXY").prop("disabled", true)
    uiServices.call(
      command,
      { layer: layer },
      function(data) {
        if (data && data.canceled) {
          setActivityStatus("Machine XY solve cancel requested.")
          appendActivity("info", data.message || "Cancel requested.")
        } else {
          appendActivity("info", (data && data.message) || "No active Machine XY solve to cancel.")
        }
        loadState(true)
      },
      function(response) {
        showError(responseErrorMessage(response))
        loadState(true)
      }
    )
  }

  function filteredMeasurements() {
    if (!currentState || !currentState.measurements) return []
    var layerFilter = $("#machineGeometryFilterLayer").val() || "all"
    var kindFilter = $("#machineGeometryFilterKind").val() || "all"
    var useFilter = $("#machineGeometryFilterUse").val() || "all"
    return currentState.measurements.filter(function(item) {
      if (layerFilter !== "all" && item.layer !== layerFilter) return false
      if (kindFilter !== "all" && item.kind !== kindFilter) return false
      if (useFilter === "machine" && !item.usableForMachineXY) return false
      if (useFilter === "layer_z" && !item.usableForLayerZ) return false
      if (useFilter === "either" && !item.usableForMachineXY && !item.usableForLayerZ) return false
      return true
    })
  }

  function renderWarning() {
    var warning = []
    if (!currentState) {
      $("#machineGeometryWarning").addClass("hidden").text("")
      return
    }
    if (!currentState.enabled && currentState.disabledReason) {
      warning.push(currentState.disabledReason)
    }
    if (currentState.gcodeExecutionActive) {
      warning.push("G-code execution is active. Solve preview, capture, and pruning stay available, but apply actions and manual line-offset edits are blocked.")
    }
    if (warning.length === 0) {
      $("#machineGeometryWarning").addClass("hidden").text("")
    } else {
      $("#machineGeometryWarning").removeClass("hidden").text(warning.join(" "))
    }
  }

  function renderCapture() {
    var positions = currentState ? (currentState.currentPositions || {}) : {}
    var lastTrace = currentState ? currentState.lastMotionTrace : null
    $("#machineGeometryActiveLayer").text(currentState && currentState.activeLayer ? currentState.activeLayer : "-")
    $("#machineGeometryCurrentPosition").text(
      "X " + formatNumber(positions.effectiveCameraX, 3)
      + " | Y " + formatNumber(positions.rawCameraY, 3)
      + " | Z " + formatNumber(positions.currentZ, 3)
    )
    $("#machineGeometryLastTrace").val(lastTrace && lastTrace.line ? lastTrace.line : "")

    var captureDisabled = !currentState || !currentState.enabled
    $("#machineGeometryCaptureXY").prop("disabled", captureDisabled)
    $("#machineGeometryCaptureZ").prop("disabled", captureDisabled)
    $("#machineGeometryCaptureBoth").prop("disabled", captureDisabled)
  }

  function renderMachine() {
    var machine = currentState ? currentState.machine : null
    var live = machine ? machine.live || {} : {}
    $("#machineGeometryLiveCameraX").text(formatNumber(live.cameraWireOffsetX, 3))
    $("#machineGeometryLiveCameraY").text(formatNumber(live.cameraWireOffsetY, 3))
    $("#machineGeometryNominalRollerY").text(formatNumber(live.nominalRollerY, 3))

    var rollerRows = ""
    var liveRollers = live.rollerYCals || []
    for (var index = 0; index < 4; index += 1) {
      rollerRows +=
        "<tr>"
        + "<td>" + rollerLabel(index) + "</td>"
        + '<td class="numeric">' + formatNumber(liveRollers[index], 3) + "</td>"
        + "</tr>"
    }
    $("#machineGeometryLiveRollers").html(rollerRows)

    var draftSummary = "No machine XY solve has been run."
    if (machine && machine.draft) {
      draftSummary =
        "Camera X " + formatNumber(machine.draft.cameraWireOffsetX, 3)
        + " | Camera Y " + formatNumber(machine.draft.cameraWireOffsetY, 3)
        + "\nRollers: " + (machine.draft.rollerYCals || []).map(function(value) {
          return formatNumber(value, 3)
        }).join(", ")
      if (machine.draft.objective) {
        draftSummary +=
          "\nLine norm " + formatCompactNumber(machine.draft.objective.lineOffsetNorm, 4)
          + " | Roller norm " + formatCompactNumber(machine.draft.objective.rollerOffsetNorm, 4)
          + " | Camera delta norm " + formatCompactNumber(machine.draft.objective.cameraOffsetDeltaNorm, 4)
      }
      if (machine.draftStale) {
        draftSummary += "\nDraft is stale with respect to the current measurement set."
      }
    }
    $("#machineGeometryMachineDraftSummary").text(draftSummary)

    var machineSolve = currentState && currentState.layerState ? currentState.layerState.machineSolve : null
    var machineSolveStatus = currentState && currentState.layerState
      ? currentState.layerState.machineSolveStatus
      : null
    var machineSolveRunning = machineSolveInProgress(machineSolveStatus)
    var machineSolveCancelRequested = machineSolveStatus && machineSolveStatus.status === "cancel_requested"
    var machineSolveKillRequested = machineSolveStatus && machineSolveStatus.status === "kill_requested"
    if (machineSolveStatus) {
      renderMachineSolveStatus(machineSolveStatus)
    } else {
      setActivityProgress(null)
    }
    if (activeOperation === "machine_xy" && !machineSolveRunning && progressPollTimer) {
      stopProgressPoll()
    }
    $("#machineGeometrySolveMachineXY").prop(
      "disabled",
      !currentState || !currentState.enabled || machineSolveRunning
    )
    $("#machineGeometryCancelMachineXY").prop(
      "disabled",
      !currentState || !currentState.enabled || !machineSolveRunning || !!machineSolveCancelRequested || !!machineSolveKillRequested
    )
    $("#machineGeometryKillMachineXY").prop(
      "disabled",
      !currentState || !currentState.enabled || !machineSolveRunning || !!machineSolveKillRequested
    )
    $("#machineGeometryApplyMachineXY").prop(
      "disabled",
      !currentState
      || !currentState.enabled
      || machineSolveRunning
      || currentState.gcodeExecutionActive
      || !machine
      || !machine.draft
      || !machineSolve
      || !!machineSolve.fitError
    )
  }

  function renderLineOffsetTable(bodySelector, items, editable) {
    var rows = ""
    if (!items || items.length === 0) {
      rows = '<tr><td colspan="' + (editable ? 4 : 4) + '">None</td></tr>'
    } else {
      items.forEach(function(item) {
        rows +=
          "<tr>"
          + "<td>" + item.lineKey + "</td>"
          + '<td class="numeric">' + formatNumber(item.x, 3) + "</td>"
          + '<td class="numeric">' + formatNumber(item.y, 3) + "</td>"
        if (editable) {
          rows +=
            "<td>"
            + '<button type="button" class="machineGeometryMiniButton machineGeometryUseOffset"'
            + ' data-line-key="' + item.lineKey + '"'
            + ' data-x="' + item.x + '"'
            + ' data-y="' + item.y + '">Use</button> '
            + '<button type="button" class="machineGeometryMiniButton machineGeometryDeleteOffsetRow"'
            + ' data-line-key="' + item.lineKey + '">Delete</button>'
            + "</td>"
        } else {
          rows += "<td>" + ((item.measurementIds || []).length || "-") + "</td>"
        }
        rows += "</tr>"
      })
    }
    $(bodySelector).html(rows)
  }

  function renderLayer() {
    var layerState = currentState ? currentState.layerState : null
    var livePlane = layerState ? layerState.liveZPlaneCalibration : null
    var draftPlane = layerState ? layerState.draftZPlaneCalibration : null

    $("#machineGeometryLivePlane").text(planeText(livePlane))
    $("#machineGeometryLivePlaneStatus").text(planeStatus(livePlane, false))
    $("#machineGeometryDraftPlane").text(planeText(draftPlane))
    $("#machineGeometryDraftPlaneStatus").text(
      planeStatus(draftPlane, layerState ? !!layerState.draftZPlaneStale : false)
    )

    renderLineOffsetTable(
      "#machineGeometryCurrentLineOffsets",
      layerState ? layerState.currentLineOffsetOverrideItems || [] : [],
      true
    )
    renderLineOffsetTable(
      "#machineGeometryDraftLineOffsets",
      layerState ? layerState.draftLineOffsetOverrideItems || [] : [],
      false
    )

    $("#machineGeometrySolveLayerZ").prop("disabled", !currentState || !currentState.enabled)
    $("#machineGeometryApplyLayerZ").prop(
      "disabled",
      !currentState
      || !currentState.enabled
      || currentState.gcodeExecutionActive
      || !draftPlane
      || !!draftPlane.fit_error
      || !draftPlane.coefficients
    )
    $("#machineGeometrySetLineOffset").prop(
      "disabled",
      !currentState || !currentState.enabled || currentState.gcodeExecutionActive
    )
    $("#machineGeometryDeleteLineOffset").prop(
      "disabled",
      !currentState || !currentState.enabled || currentState.gcodeExecutionActive
    )
  }

  function renderMeasurements() {
    var items = filteredMeasurements().slice().reverse()
    $("#machineGeometryMeasurementCount").text(
      items.length === 0
        ? "No measurements match the current filters."
        : items.length + " measurement" + (items.length === 1 ? "" : "s") + " shown."
    )

    var rows = ""
    if (items.length === 0) {
      rows = '<tr><td colspan="9">No measurements recorded.</td></tr>'
    } else {
      items.forEach(function(item) {
        rows +=
          "<tr>"
          + "<td>" + item.id + "</td>"
          + "<td>" + (item.layer || "-") + "</td>"
          + "<td>" + (item.kind || "-") + "</td>"
          + "<td>" + (item.lineKey || "-") + "</td>"
          + '<td class="numeric">' + formatNumber(item.actualWireX, 3) + "</td>"
          + '<td class="numeric">' + formatNumber(item.actualWireY, 3) + "</td>"
          + '<td class="numeric">' + formatNumber(item.actualZ, 3) + "</td>"
          + "<td>" + measurementUseText(item) + "</td>"
          + "<td>"
          + '<button type="button" class="machineGeometryMiniButton machineGeometryDeleteMeasurement" data-id="' + item.id + '">Delete</button>'
          + "</td>"
          + "</tr>"
      })
    }
    $("#machineGeometryMeasurements").html(rows)
  }

  function render() {
    renderWarning()
    renderCapture()
    renderMachine()
    renderLayer()
    renderMeasurements()
  }

  function activeLayer() {
    return currentState && currentState.activeLayer ? currentState.activeLayer : null
  }

  function requireLineKey() {
    var lineKey = ($("#machineGeometryLineKey").val() || "").trim()
    if (!lineKey) {
      showError("Line key is required.")
      return null
    }
    return lineKey
  }

  $("#machineGeometryRefresh").off("click").on("click", function() {
    loadState(true)
  })

  $("#machineGeometryCaptureXY").off("click").on("click", function() {
    callAndRefresh(
      commandName(commands.process.machineGeometryRecordMeasurement, "process.machine_geometry.record_measurement"),
      { layer: activeLayer(), capture_xy: true, capture_z: false },
      "Captured XY measurement.",
      true
    )
  })

  $("#machineGeometryCaptureZ").off("click").on("click", function() {
    callAndRefresh(
      commandName(commands.process.machineGeometryRecordMeasurement, "process.machine_geometry.record_measurement"),
      { layer: activeLayer(), capture_xy: false, capture_z: true },
      "Captured Z measurement.",
      true
    )
  })

  $("#machineGeometryCaptureBoth").off("click").on("click", function() {
    callAndRefresh(
      commandName(commands.process.machineGeometryRecordMeasurement, "process.machine_geometry.record_measurement"),
      { layer: activeLayer(), capture_xy: true, capture_z: true },
      "Captured XY + Z measurement.",
      true
    )
  })

  $("#machineGeometrySolveLayerZ").off("click").on("click", function() {
    callAndRefresh(
      commandName(commands.process.machineGeometrySolveLayerZ, "process.machine_geometry.solve_layer_z"),
      { layer: activeLayer() },
      "Solved layer Z draft.",
      true
    )
  })

  $("#machineGeometryApplyLayerZ").off("click").on("click", function() {
    callAndRefresh(
      commandName(commands.process.machineGeometryApplyLayerZ, "process.machine_geometry.apply_layer_z"),
      { layer: activeLayer() },
      "Applied layer Z calibration.",
      true
    )
  })

  $("#machineGeometrySolveMachineXY").off("click").on("click", function() {
    beginMachineXYSolve()
  })

  $("#machineGeometryCancelMachineXY").off("click").on("click", function() {
    cancelMachineXYSolve()
  })

  $("#machineGeometryKillMachineXY").off("click").on("click", function() {
    killMachineXYSolve()
  })

  $("#machineGeometryApplyMachineXY").off("click").on("click", function() {
    callAndRefresh(
      commandName(commands.process.machineGeometryApplyMachineXY, "process.machine_geometry.apply_machine_xy"),
      { layer: activeLayer() },
      "Applied machine XY calibration and regenerated the active recipe.",
      true
    )
  })

  $("#machineGeometrySetLineOffset").off("click").on("click", function() {
    var lineKey = requireLineKey()
    if (!lineKey) return
    var xValue = parseFloat($("#machineGeometryLineOffsetX").val())
    var yValue = parseFloat($("#machineGeometryLineOffsetY").val())
    if (!$.isNumeric(xValue) || !$.isNumeric(yValue)) {
      showError("Both line-offset values are required.")
      return
    }
    callAndRefresh(
      commandName(commands.process.machineGeometrySetLineOffsetOverride, "process.machine_geometry.set_line_offset_override"),
      { layer: activeLayer(), line_key: lineKey, x: xValue, y: yValue },
      "Updated live line offset.",
      true
    )
  })

  $("#machineGeometryDeleteLineOffset").off("click").on("click", function() {
    var lineKey = requireLineKey()
    if (!lineKey) return
    callAndRefresh(
      commandName(commands.process.machineGeometryDeleteLineOffsetOverride, "process.machine_geometry.delete_line_offset_override"),
      { layer: activeLayer(), line_key: lineKey },
      "Deleted live line offset.",
      true
    )
  })

  $("#machineGeometryFilterLayer, #machineGeometryFilterKind, #machineGeometryFilterUse")
    .off("change")
    .on("change", function() {
      renderMeasurements()
    })

  $(document)
    .off("click.machineGeometry")
    .on("click.machineGeometry", ".machineGeometryDeleteMeasurement", function() {
      var measurementId = $(this).data("id")
      callAndRefresh(
        commandName(commands.process.machineGeometryDeleteMeasurement, "process.machine_geometry.delete_measurement"),
        { measurement_id: measurementId },
        "Deleted measurement " + measurementId + ".",
        true
      )
    })
    .on("click.machineGeometry", ".machineGeometryUseOffset", function() {
      $("#machineGeometryLineKey").val($(this).data("line-key"))
      $("#machineGeometryLineOffsetX").val($(this).data("x"))
      $("#machineGeometryLineOffsetY").val($(this).data("y"))
    })
    .on("click.machineGeometry", ".machineGeometryDeleteOffsetRow", function() {
      var lineKey = $(this).data("line-key")
      $("#machineGeometryLineKey").val(lineKey)
      callAndRefresh(
        commandName(commands.process.machineGeometryDeleteLineOffsetOverride, "process.machine_geometry.delete_line_offset_override"),
        { layer: activeLayer(), line_key: lineKey },
        "Deleted live line offset.",
        true
      )
    })

  loadState(false)

  modules.registerShutdownCallback(function() {
    stopProgressPoll()
    $(document).off("click.machineGeometry")
  })
}
