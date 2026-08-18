# Candidate Detection and Deterministic Verification

Candidate detection exists to improve duplicate recall without giving fuzzy similarity merge authority.

Built-in `lexical` uses lexical blocking plus Jaccard/sequence similarity. Host runtimes may register embedding-backed providers.

Every proposed pair passes `verify_candidate()`:

- exact normalized claim -> safe duplicate;
- exact canonical/structured identity + exact structured assertion side -> safe duplicate;
- exact identity + different structured side -> contradiction candidate;
- missing deterministic identity -> insufficient identity;
- matching identity without enough assertion structure -> unverified assertion.

The fan-in reducer does not automatically merge candidate pairs. This preserves the project's false-negative-over-false-positive policy.
