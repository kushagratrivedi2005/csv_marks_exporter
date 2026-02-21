import os
from tutor import hooks

# ── STEP 1: Register templates folder ─────────────────────────────────────────

template_folder = os.path.join(os.path.dirname(__file__), "templates")
hooks.Filters.ENV_TEMPLATE_ROOTS.add_item(template_folder)

# Copies templates/csv_grader/ into env/build/openedx/csv_grader_app/
hooks.Filters.ENV_TEMPLATE_TARGETS.add_item(
    ("csv_grader", "build/openedx/csv_grader_app")
)

# ── STEP 2: LMS settings ───────────────────────────────────────────────────────

hooks.Filters.ENV_PATCHES.add_item((
    "openedx-lms-common-settings",
    'INSTALLED_APPS += ["csv_grader"]'
))

# ── STEP 3: CMS (Studio) settings ─────────────────────────────────────────────

hooks.Filters.ENV_PATCHES.add_item((
    "openedx-cms-common-settings",
    """INSTALLED_APPS += ["csv_grader"]
ADVANCED_COMPONENT_TYPES = list(globals().get("ADVANCED_COMPONENT_TYPES", []))
if "csv_grader" not in ADVANCED_COMPONENT_TYPES:
    ADVANCED_COMPONENT_TYPES += ["csv_grader"]"""
))

# ── STEP 4: Dockerfile — copy app + register XBlock entry point ───────────────

hooks.Filters.ENV_PATCHES.add_item((
    "openedx-dockerfile-post-python-requirements",
    r"""COPY --chown=app:app ./csv_grader_app/csv_grader /openedx/venv/lib/python3.11/site-packages/csv_grader
RUN mkdir -p /tmp/csvpkg && \
    printf '[metadata]\nname = csv-grader\nversion = 0.1\n\n[options]\npackages = find:\npackage_dir = =src\n\n[options.entry_points]\nxblock.v1 =\n    csv_grader = csv_grader.xblock_csv_grader:CsvGraderXBlock\n' > /tmp/csvpkg/setup.cfg && \
    printf 'from setuptools import setup\nsetup()\n' > /tmp/csvpkg/setup.py && \
    mkdir -p /tmp/csvpkg/src && \
    ln -s /openedx/venv/lib/python3.11/site-packages/csv_grader /tmp/csvpkg/src/csv_grader && \
    cd /tmp/csvpkg && /openedx/venv/bin/pip install -e . --no-deps -q"""
))