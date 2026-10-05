"""Isolate each test run in its own data directory.

Must run before any app.* import, since the settings are resolved at import
time.
"""

import os
import tempfile

os.environ["AWTRIXNG_DATA_DIR"] = tempfile.mkdtemp(prefix="awtrixng-tests-")
