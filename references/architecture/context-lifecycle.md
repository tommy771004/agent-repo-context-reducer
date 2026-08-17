# Context lifecycle

Session state tracks hot/warm/cold metadata and symbol fingerprints. Unchanged symbols may be emitted as references; changed symbols may use deltas. Lifecycle metadata does not claim to evict tokens already sent to a model.
