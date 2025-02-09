"""Run local development server for blockchain metrics collection."""

import json
import os
import sys
from http.server import HTTPServer
from pathlib import Path

import dotenv

project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)


def setup_environment():
    """Load environment and endpoints configuration."""
    env_path = Path(project_root) / ".env.local"
    print(f"Looking for .env.local at: {env_path}")

    dotenv.load_dotenv(env_path)
    endpoints_path = Path(project_root) / "endpoints.json"

    with open(endpoints_path) as f:
        os.environ["ENDPOINTS"] = json.dumps(json.load(f))


def main():
    """Start local development server."""
    setup_environment()

    # Import handler after environment setup
    from api.read.solana import handler as SolanaHandler

    server = HTTPServer(("localhost", 8000), SolanaHandler)
    print("Server started at http://localhost:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
