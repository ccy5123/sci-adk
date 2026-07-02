# sci-adk: Lean 4 formal-proof checker environment (image: sci-adk-lean)
#
# The container the Lean formal-proof capability (src/sci_adk/adapter/lean_capability.py)
# runs the checker in: `docker run --rm -v <ws>:/workspace -w /workspace sci-adk-lean
# lean <proof.lean>`. Exit 0 => the capability emits a decisive FORMAL_PROOF; non-zero =>
# an inconclusive PROOF_STEP (a failed compile is not a counterexample).
#
# RECIPE ONLY -- NOT built or verified in CI (Lean 4 + Mathlib is multi-GB and needs the
# toolchain). Build it on a machine with Docker:
#     docker build -t sci-adk-lean environments/lean-base
# then point the capability at it (default image name is already `sci-adk-lean`), or override
# via lean_experiment(..., image="my-lean-image").
#
# Mathlib note: importing Mathlib requires a matching toolchain + a cached build (a bare
# `lake build` of Mathlib is very slow). For real use, pin a Mathlib release whose
# lean-toolchain this image installs, and pre-build the cache (`lake exe cache get`) so the
# per-proof `lean` invocation only elaborates the user's file, not all of Mathlib.

FROM ubuntu:24.04

WORKDIR /workspace

# elan (the Lean toolchain manager) needs curl + git; ca-certificates for TLS.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install elan (pins the Lean toolchain from a project's lean-toolchain file at build time).
# -y installs without prompting; the default toolchain is set to the pinned stable channel.
RUN curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.elan/bin:${PATH}"

# Bake the stable toolchain INTO the image. elan is lazy (it only records the default and
# downloads Lean on first use), so without this every `docker run --rm ... lean` would
# re-download the toolchain. Forcing `lean --version` at build time caches it in the layer.
RUN lean --version

# OPTIONAL (recommended for real use): a Mathlib-enabled Lake project pre-built so `import
# Mathlib` resolves without rebuilding it per proof. Uncomment + pin a release:
#   RUN lake +stable new mathlib_env math && cd mathlib_env \
#       && lake exe cache get && lake build
# and run proofs against that project's env:
#   lake env lean /workspace/proof.lean
# The capability calls `lean <file>`; for a Mathlib import, wire it through `lake env`.

CMD ["lean", "--version"]
