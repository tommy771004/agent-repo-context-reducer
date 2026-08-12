# Security Policy

## Trust model

Agent Repo Context Reducer scans local repositories and emits structural metadata. It is designed to reduce accidental ingestion of secrets and unrelated filesystem content, but it is not a secret scanner or sandbox.

## Default protections

The scanner skips:

- `.env` / `.env.*`
- paths containing common `secret` or `credential` names
- private-key-like extensions and SSH private key names
- symlinks
- binary files
- files over the configured size limit
- generated/minified code by default
- common vendor/build/cache directories

`inspect` refuses secret-like paths.

## What is not guaranteed

Secrets can exist in ordinary source files with ordinary names. The tool does not inspect values and cannot guarantee that output contains no sensitive identifiers or literals exposed through function/type/route signatures.

Review repository trust boundaries before running tools in sensitive environments.

## Reporting

Please report security-sensitive issues privately through GitHub's security advisory mechanism when available rather than opening a public issue with exploit or secret material.
