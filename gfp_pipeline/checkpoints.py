import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen


MODELS = ("rfd3", "ligandmpnn", "rf3")
READ_TIMEOUT_SECONDS = 90


def content_length(response):
    length = int(response.headers.get("Content-Length", "0"))
    if length <= 0:
        raise ValueError("Checkpoint server returned no valid Content-Length.")
    return length


def cached_checkpoint_is_complete(info, path):
    if not path.is_file():
        return False
    if info.sha256:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest() == info.sha256
    # Older Foundry installs wrote directly to the final filename.
    request = Request(info.url, method="HEAD")
    with urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:
        return path.stat().st_size == content_length(response)


def download_checkpoint(name, info, directory):
    path = directory / info.filename
    if cached_checkpoint_is_complete(info, path):
        print(f"{name}: using cached {path.name}", flush=True)
        return

    print(f"{name}: downloading {path.name}", flush=True)
    with NamedTemporaryFile(dir=directory, prefix=path.name + ".", suffix=".part",
                            delete=False) as handle:
        temporary = Path(handle.name)
    try:
        digest = hashlib.sha256() if info.sha256 else None
        with urlopen(info.url, timeout=READ_TIMEOUT_SECONDS) as response, temporary.open("wb") as handle:
            expected = content_length(response)
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
                if digest:
                    digest.update(chunk)
        received = temporary.stat().st_size
        if received != expected:
            raise ValueError(f"{name}: received {received} of {expected} bytes.")
        if digest and digest.hexdigest() != info.sha256:
            raise ValueError(f"{name}: checkpoint SHA-256 mismatch.")
        temporary.replace(path)
        print(f"{name}: ready ({received / 10**6:,.1f} MB)", flush=True)
    finally:
        temporary.unlink(missing_ok=True)


def install_checkpoints(registry, directory):
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        downloads = [pool.submit(download_checkpoint, name, registry[name], directory)
                     for name in MODELS]
        for download in downloads:
            download.result()


if __name__ == "__main__":
    from foundry_cli.checkpoints import REGISTERED_CHECKPOINTS

    install_checkpoints(REGISTERED_CHECKPOINTS, Path(sys.argv[1]))
