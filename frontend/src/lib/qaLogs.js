// Capture completion is independent of the test result and retention status.
const CAPTURE_ERRORS = new Set(["log_size_limit", "log_storage_error"]);
export const logCaptureErrorKey = (reason) => CAPTURE_ERRORS.has(reason) ? "qaLog.errors." + reason : null;
