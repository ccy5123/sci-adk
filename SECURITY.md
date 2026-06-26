# Security Policy

## Supported versions

sci-adk is pre-1.0. Security fixes are applied to the latest `0.1.x` development
state on `master`. There is no long-term support branch yet.

| Version | Supported |
|---------|-----------|
| `master` (0.1.x) | yes |
| older commits | no |

## Reporting a vulnerability

Please report security-sensitive issues **privately**, not as public GitHub
issues:

- Email: ccy5123ccy@gmail.com
- Or open a private advisory via GitHub Security Advisories on this repository.

Include the affected component, a reproduction, and the impact you observed. You
will get an acknowledgement, and a fix or mitigation will be worked as promptly
as possible. Please give a reasonable window before any public disclosure.

## Scope note — code execution

sci-adk runs experiment code in an isolated Docker container
(`src/sci_adk/runner/docker_executor.py`). Treat any proposal/capability you did
not author as untrusted input: run it only in the Docker path, never on the host.
Reports about the isolation boundary (container escape, provenance tampering,
or a way to make a recorded Claim reproduce against a forged record) are in scope
and especially valued.
