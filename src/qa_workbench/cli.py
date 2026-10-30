"""Run a standalone workbench with an explicitly selected project adapter."""
import argparse
import hmac
import importlib
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", help="Installed module:factory returning a ProjectAdapter")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--archive-root", default=".qa-workbench/data")
    parser.add_argument("--token-env", help="Environment variable holding an access token; never use a literal token argument")
    parser.add_argument("--frontend-dir", help="Built standalone frontend directory")
    args = parser.parse_args(argv)
    adapter, authenticate = None, None
    if args.adapter is not None:
        module, separator, factory = args.adapter.partition(":")
        if not separator or not module or not factory:
            parser.error("adapter must name an installed module:factory")
        try:
            adapter_module = importlib.import_module(module)
        except ModuleNotFoundError as error:
            if error.name and (module == error.name or module.startswith(error.name + ".")):
                parser.error("adapter must name an installed module:factory")
            raise
        try:
            create_adapter = getattr(adapter_module, factory)
        except AttributeError:
            parser.error("adapter must name an installed module:factory")
        if not callable(create_adapter):
            parser.error("adapter must name an installed module:factory")
        adapter = create_adapter()
    if args.token_env:
        secret = os.environ.get(args.token_env, "")
        if len(secret) < 24:
            parser.error("access token environment variable must contain at least 24 characters")
        def authenticate(request):
            from fastapi import HTTPException
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + secret).encode("utf-8")):
                raise HTTPException(401, "authentication_required")
            return "token-owner"
    elif adapter is not None or args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("custom adapters and externally bound hosts require --token-env or a custom authenticated host app")
    import uvicorn

    from .app import create_app
    app = create_app(adapter, archive_root=Path(args.archive_root), authenticate=authenticate,
                     frontend_dir=args.frontend_dir)
    uvicorn.run(app, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
