# Plan: Enable layer change without a loaded recipe

## Context

On first load (or when no recipe file is available for a layer), the APA page's layer dropdown is non-functional. `selectLayer()` in `APA.js` only calls the backend if it finds a matching `<layer>-layer.gc` file — when none exists, the backend layer stays `null`. This blocks calibration and G-code generation workflows that depend on the active layer.

## Changes required

### 1. `src/dune_winder/core/winder_workspace.py`
Add a `setLayer(layer)` method that updates `_layer`, derives the calibration filename, and reloads calibration — without touching the G-code handler or recipe.

```python
def setLayer(self, layer):
    self._layer = layer
    self._calibrationFile = self._layer + "_Calibration.json" if self._layer is not None else None
    if self._calibrationFile:
        self._loadCalibrationFromDisk()
    else:
        self._useCalibration(None)
    self._saveState()
```

### 2. `src/dune_winder/api/commands.py`
Register a new command after the existing `process.get_recipe_layer` block (~line 661):

```python
def process_set_recipe_layer(args):
    _validateArgs(args, required=("layer",))
    if process.workspace is None:
        raise ValueError("No workspace is loaded.")
    layer = _asString(args["layer"], "layer")
    process.workspace.setLayer(layer)
    return None

registry.register("process.set_recipe_layer", process_set_recipe_layer, True)
```

### 3. `dune_winder/web/Scripts/CommandCatalog.js`
Add a new entry in the `process` block (after `getRecipeLayer`):

```js
setRecipeLayer: "process.set_recipe_layer",
```

### 4. `dune_winder/web/Desktop/Pages/APA.js`
Modify `selectLayer()` to call `setRecipeLayer` when no matching recipe is found:

```js
this.selectLayer = function () {
    var layer = $("#layerSelection").val();
    var defaultRecipe = (layer + "-layer.gc").toLowerCase();

    call(commands.process.getRecipes, {}, function (recipes) {
        var matchedRecipe = "";
        for (var i = 0; recipes && i < recipes.length; i += 1) {
            if (recipes[i].toLowerCase() === defaultRecipe) {
                matchedRecipe = recipes[i];
                break;
            }
        }

        if (matchedRecipe) {
            $("#gCodeSelection").val(matchedRecipe);
            self.selectG_Code();
        } else {
            // No recipe for this layer — update the active layer only.
            call(commands.process.setRecipeLayer, { layer: layer });
        }
    });
};
```

## Files to modify

| File | Change |
|------|--------|
| `src/dune_winder/core/winder_workspace.py` | Add `setLayer()` method |
| `src/dune_winder/api/commands.py` | Register `process.set_recipe_layer` command |
| `dune_winder/web/Scripts/CommandCatalog.js` | Add `setRecipeLayer` catalog entry |
| `dune_winder/web/Desktop/Pages/APA.js` | Call `setRecipeLayer` in `selectLayer()` fallback |

## Verification

1. Start the winder app with no `u-layer.gc` or `v-layer.gc` in the recipe directory
2. Open the APA page; select "U" from the layer dropdown
3. Confirm the backend now reports `U` when `getRecipeLayer` is polled (visible in GCodeGeneration page)
4. Confirm the calibration panel on the GCodeGeneration / Calibrate tab reflects the correct layer
5. Run `uv run pytest tests/dune_winder/` to ensure no regressions
