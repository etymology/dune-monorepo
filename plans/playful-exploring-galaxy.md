# PESTO Pitch Detection Optimization with ONNX Runtime

## Context

The DUNE APA winder uses PESTO (PyTorch-based deep learning pitch detection) for real-time wire tension measurement. During sweep operations, many audio windows are queued for pitch analysis, but the current Python/PyTorch implementation causes performance issues:

- **Latency bottleneck**: `AsyncPitchWorker` processes all pitch jobs in a single Python thread
- **GIL contention**: PyTorch inference is GIL-bound, preventing true parallelism
- **Queue backups**: During sweeps, the pitch queue (max 64 jobs) fills up and sweep jobs are dropped
- **Typical inference time**: 10-50ms per window, accumulating to seconds of backlog

The goal is to optimize PESTO inference speed by exporting to ONNX format and using ONNX Runtime's C++ backend, which provides 2-10x speedup and eliminates GIL issues.

## Implementation Approach

### Phase 1: Model Export Infrastructure

**Create export script** (`src/spectrum_analysis/export_pesto_onnx.py`):
- Load PESTO model with PyTorch
- Create dummy inputs for tracing (dynamic audio length, configurable sampling rate)
- Export model to ONNX format with proper input/output specifications
- Handle HCQT preprocessing complexity (dynamic kernel computation based on sampling rate)
- Export model weights to `dune_tension/data/pesto_onnx/` directory
- Support multiple model variants (mir-1k_g7, etc.)

**Design decision**: Keep HCQT preprocessing in Python (chosen for safety and compatibility)

**Key implementation points**:
- Export only the CNN encoder (Resnet1d) and confidence classifier to ONNX
- HCQT preprocessing remains in Python using existing pesto.preprocessor
- This avoids dynamic kernel computation issues with sampling rate
- Confidence classifier exported alongside encoder for parallel inference
- Activation reduction (alwa method) kept in Python for flexibility

### Phase 2: ONNX Runtime Wrapper

**Create ONNX runtime module** (`src/spectrum_analysis/pesto_onnx.py`):
- `load_onnx_model()`: Load exported ONNX model and cache instances
- `ONNXPestoModel` class: Wrapper around ONNX Runtime session
  - Handle dynamic input shapes
  - Perform HCQT preprocessing (if not in ONNX graph)
  - Run inference with ONNX Runtime
  - Convert outputs to match PyTorch format (freq, confidence, activations)
- `estimate_pitch_with_onnx()`: Drop-in replacement for `estimate_pitch_from_audio()`
- `analyze_audio_with_onnx()`: Drop-in replacement for `analyze_audio_with_pesto()`

**Design decisions**:
- Keep preprocessing in Python if HCQT can't be easily exported to ONNX
- Use ONNX Runtime only for the neural network inference (encoder + confidence)
- Maintain same output types as PyTorch version for compatibility

### Phase 3: Backend Selection Layer

**Update [pesto_analysis.py](src/spectrum_analysis/pesto_analysis.py)**:
- Add backend selection logic (PyTorch vs ONNX Runtime)
- Add environment variable `PESTO_BACKEND=onnx|pytorch` for runtime selection
- Modify `_load_pesto_model_cached()` to support both backends
- Add `use_onnx_backend()` helper function
- Fallback to PyTorch if ONNX Runtime unavailable or export missing

**Configuration**:
- Add to `StreamingAnalysisConfig`: `use_onnx_backend: bool = False` (default off for safety)
- Allow per-session backend selection via environment variable

### Phase 4: Update AsyncPitchWorker

**Update [analysis.py](src/dune_tension/streaming/analysis.py)** (minimal changes):
- Pass backend preference to analyze function
- No structural changes to AsyncPitchWorker itself
- The optimization is transparent to the worker architecture

### Phase 5: Testing and Benchmarking

**Create benchmarks** (`tests/dune_tension/benchmark_pesto_backends.py`):
- Measure inference latency for PyTorch vs ONNX Runtime
- Test with various audio lengths and sampling rates
- Verify output accuracy (pitch and confidence within 1% tolerance)
- Test thread scaling (run multiple workers in parallel)

**Update existing tests**:
- Modify `test_pesto_analysis.py` to test both backends
- Add environment variable fixtures to run tests with each backend
- Verify ONNX backend produces identical results to PyTorch

### Phase 6: Deployment and Gradual Rollout

**Dependency updates** (`pyproject.toml`):
- Add `onnxruntime>=1.16.0` as optional dependency
- Keep `pesto-pitch>=2.0.1` as required (for fallback and model loading)

**Model export**:
- Run export script during deployment or as part of build process
- Ship ONNX models with the application
- Provide script for re-exporting if new PESTO version is needed

**Rollout strategy**:
- Default to PyTorch backend (safe, no behavior changes)
- Enable ONNX backend via environment variable for testing
- After validation, change default to ONNX in future release

## Critical Files to Modify

1. **New files**:
   - `src/spectrum_analysis/export_pesto_onnx.py` - Model export script
   - `src/spectrum_analysis/pesto_onnx.py` - ONNX Runtime wrapper
   - `tests/dune_tension/benchmark_pesto_backends.py` - Performance benchmarks
   - `dune_tension/data/pesto_onnx/` - Directory for exported models

2. **Modified files**:
   - `src/spectrum_analysis/pesto_analysis.py` - Backend selection logic
   - `pyproject.toml` - Add onnxruntime dependency
   - `tests/dune_tension/test_pesto_analysis.py` - Test both backends

3. **No structural changes needed**:
   - `src/dune_tension/streaming/analysis.py` - AsyncPitchWorker (only needs config change)
   - `src/dune_tension/streaming/controller.py` - No changes required

## Existing Code to Reuse

- `_MODEL_CACHE` pattern from [pesto_analysis.py:14](src/spectrum_analysis/pesto_analysis.py#L14) - cache ONNX models similarly
- `PestoAnalysisResult` dataclass - same return type for ONNX backend
- `FastFrameAnalyzer` frame analysis - unchanged, only pitch inference is optimized
- `AsyncPitchWorker` queue management - unchanged, just faster processing

## Verification

1. **Unit tests**:
   ```bash
   # Test both backends
   PESTO_BACKEND=pytorch pytest tests/dune_tension/test_pesto_analysis.py
   PESTO_BACKEND=onnx pytest tests/dune_tension/test_pesto_analysis.py
   ```

2. **Accuracy verification**:
   - Run same audio through both backends
   - Verify pitch predictions match within 0.1% (0.5 Hz at 500 Hz)
   - Verify confidence values match within 1%

3. **Performance benchmarks**:
   ```bash
   python tests/dune_tension/benchmark_pesto_backends.py
   ```
   - Expected: ONNX Runtime 2-5x faster than PyTorch
   - Test with 100ms, 500ms, 1s audio segments
   - Verify no GIL contention in multi-threaded test

4. **Integration test**:
   - Run full sweep with ONNX backend
   - Monitor queue backlog (should be minimal)
   - Verify tension results match PyTorch baseline

5. **Fallback test**:
   - Run with ONNX backend but delete ONNX model files
   - Verify graceful fallback to PyTorch
   - Test with missing onnxruntime package

## Expected Performance Improvement

- **Single-threaded latency**: 2-5x speedup (10-50ms → 2-10ms per window)
- **Multi-threaded scaling**: Near-linear scaling (no GIL contention)
- **Queue backlog**: Eliminated during typical sweeps
- **Memory usage**: Reduced (~30-50% less than PyTorch)

## Risks and Mitigations

**Risk**: HCQT preprocessing complexity makes ONNX export difficult
- **Mitigation**: Keep preprocessing in Python, only export CNN encoder

**Risk**: Numerical differences between PyTorch and ONNX Runtime
- **Mitigation**: Comprehensive accuracy tests, tight tolerance verification

**Risk**: ONNX Runtime not available in all deployment environments
- **Mitigation**: Graceful fallback to PyTorch, make ONNX optional dependency

**Risk**: Dynamic sampling rates (sr augmentation) complicate ONNX export
- **Mitigation**: Export separate models for common rates, or keep preprocessing in Python

## Rollback Plan

If issues arise:
1. Set `PESTO_BACKEND=pytorch` environment variable
2. Or set `use_onnx_backend=False` in config
3. System automatically uses PyTorch backend
4. No code rollback required, just configuration change
