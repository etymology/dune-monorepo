function ZPlaneCalibrate(modules) {
  try {
    var page = modules.get("Page")
    page.load("/Desktop/Pages/MachineGeometryCalibrate", "#main")
  } catch (e) {
    console.error("Failed to redirect ZPlaneCalibrate: " + e.message)
  }
}
