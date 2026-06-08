function RollerCalibrate(modules) {
  try {
    var page = modules.get("Page")
    page.load("/Desktop/Pages/MachineGeometryCalibrate", "#main")
  } catch (e) {
    console.error("Failed to redirect RollerCalibrate: " + e.message)
  }
}
