function JogCalibration(modules) {
  var self = this;

  var winder = modules.get("Winder");
  var uiServices = modules.get("UiServices");
  var commands = uiServices.getCommands();

  var pendingPreview = null; // populated after a successful preview call
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

  var resetPreviewState = function () {
    pendingPreview = null;
    $("#jogCalLineIndex").text("-");
    $("#jogCalLineLabel").text("-");
    $("#jogCalOffsetId").text("-");
    $("#jogCalLineText").text("-");
    $("#jogCalCommandedX").text("-");
    $("#jogCalCommandedY").text("-");
    $("#jogCalCommandedZ").text("-");
    $("#jogCalDeltaX").text("-").removeClass("jogCalDeltaNonZero");
    $("#jogCalDeltaY").text("-").removeClass("jogCalDeltaNonZero");
    $("#jogCalDeltaZ").text("-").removeClass("jogCalDeltaNonZero");
    $("#jogCalApplyButton").prop("disabled", true);
    $("#jogCalCancelButton").prop("disabled", true);
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
    $("#jogCalOffsetId").text(data.offsetId || "-");
    $("#jogCalLineText").text(data.lineText || "-");
    $("#jogCalCommandedX").text(formatNumber(data.commanded && data.commanded.x));
    $("#jogCalCommandedY").text(formatNumber(data.commanded && data.commanded.y));
    $("#jogCalCommandedZ").text(formatNumber(data.commanded && data.commanded.z));
    setDeltaCell("#jogCalDeltaX", data.delta && data.delta.x);
    setDeltaCell("#jogCalDeltaY", data.delta && data.delta.y);
    setDeltaCell("#jogCalDeltaZ", data.delta && data.delta.z);
    $("#jogCalApplyButton").prop("disabled", false);
    $("#jogCalCancelButton").prop("disabled", false);
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
  // Periodic poll: keep the live actual-position cells fresh so the
  // operator sees their jog moves reflected before clicking the button.
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
  // Action handlers
  // ---------------------------------------------------------------------
  var onUseCurrentClick = function () {
    setStatus("Reading positions...");
    uiServices.call(
      commands.process.vTemplatePreviewJogCalibration,
      {},
      function (data) {
        renderPreview(data || {});
        setStatus(
          "Review the delta below, then click Apply to commit and regenerate.",
        );
      },
      function (response) {
        resetPreviewState();
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
        resetPreviewState();
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
