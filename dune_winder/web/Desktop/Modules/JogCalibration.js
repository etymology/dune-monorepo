function JogCalibration(modules) {
  var self = this;

  var winder = modules.get("Winder");
  var uiServices = modules.get("UiServices");
  var commands = uiServices.getCommands();

  var pendingPreview = null; // populated after a successful preview call
  var lastRenderedSignature = null; // line+label currently shown
  var DECIMALS = 3;

  var formatNumber = function (value) {
    if (value === null || value === undefined || isNaN(value)) {
      return "-";
    }
    return parseFloat(value).toFixed(DECIMALS);
  };

  var setStatus = function (text, kind) {
    var element = $("#jogCalStatus");
    element.removeClass("error success");
    if (kind === "error") {
      element.addClass("error");
    } else if (kind === "success") {
      element.addClass("success");
    }
    element.text(text);
  };

  var clearPendingState = function () {
    pendingPreview = null;
    $("#jogCalApplyButton").prop("disabled", true);
    $("#jogCalCancelButton").prop("disabled", true);
  };

  var resetPreviewState = function () {
    clearPendingState();
    lastRenderedSignature = null;
    $("#jogCalLineIndex").text("-");
    $("#jogCalLineLabel").text("-");
    $("#jogCalSameSide").text("-");
    $("#jogCalOffsetId").text("-");
    $("#jogCalLineText").text("-");
    $("#jogCalRenderedX").text("-");
    $("#jogCalRenderedY").text("-");
    $("#jogCalRenderedZ").text("-");
    $("#jogCalCommandedX").text("-");
    $("#jogCalCommandedY").text("-");
    $("#jogCalCommandedZ").text("-");
    $("#jogCalDeltaX").text("-").removeClass("jogCalDeltaNonZero");
    $("#jogCalDeltaY").text("-").removeClass("jogCalDeltaNonZero");
    $("#jogCalDeltaZ").text("-").removeClass("jogCalDeltaNonZero");
  };

  var setDeltaCell = function (selector, value) {
    var formatted = formatNumber(value);
    var element = $(selector).text(formatted);
    if (typeof value == "number" && Math.abs(value) >= 0.0005) {
      element.addClass("jogCalDeltaNonZero");
    } else {
      element.removeClass("jogCalDeltaNonZero");
    }
  };

  var renderPreview = function (data) {
    pendingPreview = data;
    $("#jogCalLineIndex").text(
      data.lineIndex !== null && data.lineIndex !== undefined ? data.lineIndex : "-",
    );
    $("#jogCalLineLabel").text(data.label || "-");
    if (data.sameSide === true) {
      $("#jogCalSameSide").text("same-side").removeClass("alternating");
    } else if (data.sameSide === false) {
      $("#jogCalSameSide").text("alternating-side (XY only)").addClass("alternating");
    } else {
      $("#jogCalSameSide").text("-").removeClass("alternating");
    }
    $("#jogCalOffsetId").text(data.offsetId || "-");
    $("#jogCalLineText").text(data.lineText || "-");
    var rendered = data.renderedOffset || {};
    $("#jogCalRenderedX").text(formatNumber(rendered.x));
    $("#jogCalRenderedY").text(formatNumber(rendered.y));
    $("#jogCalRenderedZ").text(formatNumber(rendered.z));
    $("#jogCalCommandedX").text(formatNumber(data.commanded && data.commanded.x));
    $("#jogCalCommandedY").text(formatNumber(data.commanded && data.commanded.y));
    $("#jogCalCommandedZ").text(formatNumber(data.commanded && data.commanded.z));
    setDeltaCell("#jogCalDeltaX", data.delta && data.delta.x);
    setDeltaCell("#jogCalDeltaY", data.delta && data.delta.y);
    setDeltaCell("#jogCalDeltaZ", data.delta && data.delta.z);
    $("#jogCalApplyButton").prop("disabled", false);
    $("#jogCalCancelButton").prop("disabled", false);
  };

  var previewSignature = function (data) {
    return JSON.stringify([
      data.lineIndex,
      data.label,
      data.lineText,
      data.offsetId,
    ]);
  };

  var extractError = function (response) {
    if (!response) return "Request failed.";
    if (response.error && typeof response.error == "object") {
      return response.error.message || JSON.stringify(response.error);
    }
    if (typeof response.error == "string") return response.error;
    if (response.data && response.data.error) return response.data.error;
    return "Request failed.";
  };

  // ---------------------------------------------------------------------
  // Periodic poll #1: keep the live actual-position cells fresh so the
  // operator sees their jog moves reflected even when no labeled line
  // is currently surfaced.
  // ---------------------------------------------------------------------
  winder.addPeriodicCallback(commands.process.getUISnapshot, function (snapshot) {
    if (!snapshot || !snapshot.axes) return;
    var axes = snapshot.axes;
    var x = axes.x ? axes.x.position : null;
    var y = axes.y ? axes.y.position : null;
    var z = axes.z ? axes.z.position : null;
    $("#jogCalActualX").text(formatNumber(x));
    $("#jogCalActualY").text(formatNumber(y));
    $("#jogCalActualZ").text(formatNumber(z));
  });

  // ---------------------------------------------------------------------
  // Periodic poll #2: ask the backend for the current jog-calibration
  // snapshot.  The backend returns ok=true only when the last executed
  // line carries a calibratable label, so this naturally filters out
  // unlabeled lines and freezes the card on the last labeled state.
  // ---------------------------------------------------------------------
  winder.addPeriodicCallback(
    commands.process.vTemplatePreviewJogCalibration,
    function (data) {
      // Backend returns null/error envelope when no calibratable line has
      // executed yet -- freeze on whatever was last shown rather than
      // clearing the card.
      if (!data || !data.label) return;
      var signature = previewSignature(data);
      if (signature === lastRenderedSignature) {
        // Same line: keep delta cells fresh while operator jogs.
        setDeltaCell("#jogCalDeltaX", data.delta && data.delta.x);
        setDeltaCell("#jogCalDeltaY", data.delta && data.delta.y);
        setDeltaCell("#jogCalDeltaZ", data.delta && data.delta.z);
        pendingPreview = data;
        return;
      }
      lastRenderedSignature = signature;
      renderPreview(data);
      setStatus("Auto-updated from line " + (data.lineIndex || "-") + ".");
    },
  );

  // ---------------------------------------------------------------------
  // Action handlers
  // ---------------------------------------------------------------------
  var onUseCurrentClick = function () {
    setStatus("Reading positions and applying...");
    uiServices.call(
      commands.process.vTemplatePreviewJogCalibration,
      {},
      function (data) {
        renderPreview(data || {});
        onApplyClick();
      },
      function (response) {
        setStatus(extractError(response), "error");
      },
    );
  };

  var onApplyClick = function () {
    if (!pendingPreview) {
      setStatus("Nothing to apply.", "error");
      return;
    }
    setStatus("Applying calibration and regenerating recipe...");
    $("#jogCalApplyButton").prop("disabled", true);
    $("#jogCalCancelButton").prop("disabled", true);
    uiServices.call(
      commands.process.vTemplateApplyJogCalibration,
      {},
      function (data) {
        if (data) {
          renderPreview(data);
        }
        var newOffset = data && data.newOffset;
        var summary =
          "Applied. New offset for " +
          (data && data.offsetId) +
          " = (" +
          formatNumber(newOffset && newOffset.x) +
          ", " +
          formatNumber(newOffset && newOffset.y) +
          ", " +
          formatNumber(newOffset && newOffset.z) +
          ").";
        if (data && data.regenerated === false) {
          summary += " (Recipe regeneration failed: " + (data.regenerationError || "") + ")";
          setStatus(summary, "error");
        } else {
          summary += " Recipe regenerated.";
          setStatus(summary, "success");
        }
        clearPendingState();
      },
      function (response) {
        setStatus(extractError(response), "error");
        $("#jogCalApplyButton").prop("disabled", false);
        $("#jogCalCancelButton").prop("disabled", false);
      },
    );
  };

  var onCancelClick = function () {
    resetPreviewState();
    setStatus("Cancelled.");
  };

  this.initialize = function () {
    resetPreviewState();
    $("#jogCalUseCurrentButton").on("click", onUseCurrentClick);
    $("#jogCalApplyButton").on("click", onApplyClick);
    $("#jogCalCancelButton").on("click", onCancelClick);
    setStatus("Idle.");
  };
}
