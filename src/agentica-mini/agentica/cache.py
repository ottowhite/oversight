"""
Async cache layer for openai clients, backend by sqlite.
"""

import asyncio
import hashlib
import json
import multiprocessing
import os
import socket
import time
from pathlib import Path

import aiohttp
import aiosqlite
from aiohttp import web
from openai import AsyncOpenAI

REDIRECT_HEADER = "X-Cache-Redirect-To"
FILE_CACHE_DIR = Path(__file__).parent / "tests/file_cache"


class CacheHandler:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None

        # Read FILE_CACHE environment variable
        self.file_cache_mode = os.environ.get("FILE_CACHE", "").lower()
        if self.file_cache_mode not in ("", "read", "write"):
            raise ValueError(
                f"Invalid FILE_CACHE value: {self.file_cache_mode}. Must be '', 'read', or 'write'"
            )

        FILE_CACHE_DIR.mkdir(exist_ok=True)  # Ensure file cache directory exists

    async def initialize(self):
        """Initialize the database connection"""
        self.db = await aiosqlite.connect(self.db_path)
        await self._init_database()

    async def close(self):
        """Close the database connection"""
        if self.db:
            await self.db.close()

    async def _init_database(self):
        """Initialize the SQLite database schema"""
        if self.db is None:
            return
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                status_code INTEGER NOT NULL,
                headers TEXT NOT NULL,
                body BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.commit()

    def _hash_request(
        self, method: str, path: str, body: bytes, redirect_url: str
    ) -> tuple[str, str]:
        """Generate a hash key for the request (including redirect URL)"""
        request_data = {
            "method": method,
            "path": path,
            "body": body.decode("utf-8", errors="ignore") if body else "",
            "redirect_url": redirect_url,
        }
        request_str = json.dumps(request_data, sort_keys=True)
        # print("CACHE KEY", request_str)
        return hashlib.sha256(request_str.encode()).hexdigest(), request_str

    async def _get_cached_response(
        self, cache_key: str
    ) -> tuple[int, dict, bytes] | None:
        """Get cached response from database"""
        if self.db is None:
            return None

        cursor = await self.db.execute(
            "SELECT status_code, headers, body FROM cache WHERE key = ?", (cache_key,)
        )
        result = await cursor.fetchone()
        await cursor.close()

        if result:
            status_code, headers_json, body = result
            headers = json.loads(headers_json)
            return status_code, headers, body
        return None

    async def _save_response(
        self, cache_key: str, status_code: int, headers: dict, body: bytes
    ):
        """Save response to database"""
        if self.db is None:
            return

        headers_json = json.dumps(headers)
        await self.db.execute(
            "INSERT OR REPLACE INTO cache (key, status_code, headers, body) VALUES (?, ?, ?, ?)",
            (cache_key, status_code, headers_json, body),
        )
        await self.db.commit()

    def _get_file_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key"""
        return FILE_CACHE_DIR / f"{cache_key}.json"

    async def _get_file_cached_response(
        self, cache_key: str
    ) -> tuple[int, dict, bytes] | None:
        """Get cached response from file cache"""
        file_path = self._get_file_cache_path(cache_key)

        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            status_code = cache_data["status_code"]
            headers = cache_data["headers"]
            # Body is stored as base64 encoded string
            import base64

            body = base64.b64decode(cache_data["body"])

            return status_code, headers, body
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error reading file cache {file_path}: {e}")
            return None

    async def _save_file_cached_response(
        self, cache_key: str, status_code: int, headers: dict, body: bytes
    ):
        """Save response to file cache"""
        file_path = self._get_file_cache_path(cache_key)

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare cache data
        import base64

        cache_data = {
            "status_code": status_code,
            "headers": headers,
            "body": base64.b64encode(body).decode("utf-8"),
            "timestamp": time.time(),
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"Error writing file cache {file_path}: {e}")

    async def _forward_request(
        self,
        method: str,
        path: str,
        headers: dict,
        body: bytes,
        redirect_url: str,
        stream_response: web.StreamResponse,
        request: web.Request,
    ) -> tuple[int, dict, bytes]:
        """Forward request and stream response while collecting for cache"""
        url = f"{redirect_url.rstrip('/')}{path}"

        # Remove host header and cache redirect header to avoid conflicts
        forward_headers = {
            k: v
            for k, v in headers.items()
            if k.lower() not in ("host", "x-cache-redirect-to")
        }

        collected_body = bytearray()

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method, url=url, headers=forward_headers, data=body
            ) as response:
                # Set response status and headers
                stream_response.set_status(response.status)

                # Clean up headers that conflict with streaming
                clean_headers = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower()
                    not in ("transfer-encoding", "content-length", "content-encoding")
                }

                # Set headers on stream response
                for key, value in clean_headers.items():
                    stream_response.headers[key] = value

                # Start the streaming response
                await stream_response.prepare(request)

                # Stream the response content with no buffering
                async for chunk in response.content.iter_any():
                    collected_body.extend(chunk)
                    await stream_response.write(chunk)

                return response.status, dict(response.headers), bytes(collected_body)

    async def handle_request(
        self, request: web.Request
    ) -> web.Response | web.StreamResponse:
        """Handle incoming HTTP request"""
        # Get redirect URL from header
        redirect_url = request.headers.get("X-Cache-Redirect-To")
        if not redirect_url:
            return web.Response(status=400, text="Missing X-Cache-Redirect-To header")

        # Read request body
        body = await request.read()

        # Generate cache key
        cache_key, cache_key_str = self._hash_request(
            request.method, request.path_qs, body, redirect_url
        )

        status_code: int
        headers: dict
        response_body: bytes

        if self.file_cache_mode == "read":
            # READONLY MODE: Must be in file cache
            db_cached = await self._get_file_cached_response(cache_key)
            if db_cached:
                # print(f"FILE CACHE HIT: {cache_key}")
                status_code, headers, response_body = db_cached

                # Clean up headers that conflict with direct body return
                # Remove encoding headers since aiohttp already handled decompression when we received the response
                clean_headers = {
                    k: v
                    for k, v in headers.items()
                    if k.lower()
                    not in ("transfer-encoding", "content-length", "content-encoding")
                }

                # Set correct content-length for the actual body
                clean_headers["Content-Length"] = str(len(response_body))

                return web.Response(
                    status=status_code, headers=clean_headers, body=response_body
                )
            else:
                message = (
                    f"Cache miss in read mode for key: {cache_key}\n\n{cache_key_str}"
                )
                if github_output := os.getenv("GITHUB_OUTPUT"):
                    with open(github_output, "a") as f:
                        f.write(f"{message}\n")  # For github actions
                raise RuntimeError(message)

        else:
            # STANDARD MODE: use SQLite cache
            db_cached = await self._get_cached_response(cache_key)

            if db_cached:
                # print(f"CACHE HIT: {cache_key}")
                status_code, headers, response_body = db_cached

                # Clean up headers that conflict with direct body return
                # Remove encoding headers since aiohttp already handled decompression when we received the response
                clean_headers = {
                    k: v
                    for k, v in headers.items()
                    if k.lower()
                    not in ("transfer-encoding", "content-length", "content-encoding")
                }

                # Set correct content-length for the actual body
                clean_headers["Content-Length"] = str(len(response_body))

                return web.Response(
                    status=status_code, headers=clean_headers, body=response_body
                )
            else:
                # print(f"CACHE MISS: {cache_key}")
                # Forward request with streaming and cache response
                stream_response = web.StreamResponse()
                status_code, headers, response_body = await self._forward_request(
                    request.method,
                    request.path_qs,
                    dict(request.headers),
                    body,
                    redirect_url,
                    stream_response,
                    request,
                )

                # Cache the response after streaming
                if 200 <= status_code < 300:
                    await self._save_response(
                        cache_key, status_code, headers, response_body
                    )

                    if self.file_cache_mode == "write":
                        # WRITE MODE: Save result to file cache
                        await self._save_file_cached_response(
                            cache_key, status_code, headers, response_body
                        )

                return stream_response


async def create_cache_app(cache_db: Path) -> web.Application:
    """Create the aiohttp application with cache handler"""
    cache_handler = CacheHandler(cache_db)
    await cache_handler.initialize()

    app = web.Application()

    # Add routes for all HTTP methods
    async def handle_all_methods(request):
        return await cache_handler.handle_request(request)

    app.router.add_route("*", "/{path:.*}", handle_all_methods)

    # Store handler reference for cleanup
    app["cache_handler"] = cache_handler

    return app


async def cache_server_async(port: int, cache_db: Path):
    """Run the async cache server"""
    app = await create_cache_app(cache_db)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "localhost", port)
    await site.start()

    try:
        # Keep the server running
        while True:
            await asyncio.sleep(1)
    finally:
        await app["cache_handler"].close()
        await runner.cleanup()


def cache_server(port: int, cache_db: Path):
    """Run the cache server in the current process"""
    asyncio.run(cache_server_async(port, cache_db))


def _wait_for_server(port: int, timeout: float = 5.0):
    """Wait for the server to be ready to accept connections"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                result = s.connect_ex(("localhost", port))
                if result == 0:  # Connection successful
                    return
        except (ConnectionRefusedError, OSError):
            pass
        time.sleep(0.01)  # Small delay between attempts
    raise TimeoutError(f"Server did not start on port {port} within {timeout} seconds")


class RequestCache:
    __port: int | None  # None if not started yet
    __cache_db: Path

    def __init__(self, cache_db: Path = Path("cache.sqlite")):
        """
        Updates the client's base_url to be a cached endpoint.
        The original base_url will need to be provided via the X-Cache-Redirect-To header in requests.
        """
        self.__port = None
        self.__cache_db = cache_db

    def __start_idempotently(self):
        if self.__port is not None:
            return

        # Find a free port by binding to port 0
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            self.__port = s.getsockname()[1]

        # Start the server in a subprocess using multiprocessing
        process = multiprocessing.Process(
            target=cache_server, args=(self.__port, self.__cache_db)
        )
        process.daemon = True  # Dies when parent process dies
        process.start()

        # Wait for the server to start
        assert self.__port is not None, (
            "If port not set, should've already thrown exception"
        )
        _wait_for_server(self.__port)

    def hook_openai(self, client: AsyncOpenAI):
        self.__start_idempotently()
        assert self.__port is not None, "Server start should've set port number"

        if REDIRECT_HEADER in client._custom_headers:
            assert client.base_url == f"http://localhost:{self.__port}/"
            return  # Makes the hook idempotent

        assert isinstance(client._custom_headers, dict), (
            "Generic mappings not supported"
        )
        client._custom_headers[REDIRECT_HEADER] = str(client.base_url)
        client.base_url = f"http://localhost:{self.__port}/"


local_cache = RequestCache(Path("cache.sqlite"))
