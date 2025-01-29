"""Run local development server for blockchain metrics collection."""

import json
import os
from http.server import HTTPServer

import dotenv


def setup_environment():
    """Load environment and endpoints configuration."""
    dotenv.load_dotenv(".env.local")
    with open("endpoints.json") as f:
        os.environ["ENDPOINTS"] = json.dumps(json.load(f))


def main():
    """Start local development server."""
    setup_environment()

    # Import handler after environment setup
    from api.write.solana import handler as SolanaHandler

    server = HTTPServer(("localhost", 8000), SolanaHandler)
    print("Server started at http://localhost:8000")
    server.serve_forever()


main()
