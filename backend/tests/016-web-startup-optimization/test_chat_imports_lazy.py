"""Chat/RAG dependencies load only when a chat handler needs them."""

import subprocess
import sys
from pathlib import Path


def test_importing_chat_router_does_not_load_chromadb():
    backend_dir = Path(__file__).resolve().parents[2]
    code = (
        "import app.routers.chat, sys; "
        "assert not any(name == 'chromadb' or name.startswith('chromadb.') "
        "for name in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
