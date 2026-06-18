# sci-adk Milestone 1: Python Base Environment
# Minimal scientific computing stack for T-1 molecular encoding experiments

FROM python:3.11-slim

# Set working directory
WORKDIR /workspace

# Install system dependencies.
# gcc/g++: build toolchain for any source builds.
# libxrender1, libxext6, libexpat1: shared libraries RDKit's Cairo 2D drawing
#   backend (rdkit.Chem.Draw.rdMolDraw2D) links against at import/draw time. The
#   rdkit manylinux wheel bundles cairo itself, but importing rdMolDraw2D still
#   dlopen()s libXrender/libXext (X libs) and libexpat (XML parser cairo pulls in);
#   none ship in python:3.11-slim, so MolDraw2DCairo fails without them. The exact
#   set was determined EMPIRICALLY by building + drawing a PNG in-container until the
#   import succeeded (paper-figures Phase 4-2): libexpat1 surfaced only after the X
#   libs were added.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libxrender1 \
    libxext6 \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Default command
CMD ["python3"]
