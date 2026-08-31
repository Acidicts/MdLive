import argparse

import uvicorn

from mdlive.server import MDLiveServer


def main():
    parser = argparse.ArgumentParser(description="Serve a Markdown file with live reload")
    parser.add_argument("file", help="Path to the .md file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = MDLiveServer(args.file)
    uvicorn.run(server.app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
