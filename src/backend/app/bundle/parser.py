"""Bundle parser — validates and extracts .tar.gz support bundles in memory."""

import io
import posixpath
import tarfile

from app.models.schemas import BundleFile, BundleManifest, SignalType

MAX_BUNDLE_SIZE = 500 * 1024 * 1024  # 500MB
MAX_EXTRACTED_SIZE = 2 * 1024 * 1024 * 1024  # 2GB decompressed
MAX_FILE_COUNT = 10_000
MAX_SINGLE_FILE_SIZE = 100 * 1024 * 1024  # 100MB per file


class InvalidBundleError(Exception):
    """Raised when the uploaded file is not a valid .tar.gz archive."""


class BundleTooLargeError(Exception):
    """Raised when the uploaded file exceeds the maximum size limit."""


def parse_bundle(file_data: bytes) -> tuple[BundleManifest, dict[str, bytes]]:
    """Parse a .tar.gz bundle, extract contents in memory, and return manifest + files.

    Raises:
        BundleTooLargeError: If compressed file exceeds 500MB or decompressed exceeds 2GB.
        InvalidBundleError: If file is not a valid tar.gz archive.
    """
    if len(file_data) > MAX_BUNDLE_SIZE:
        raise BundleTooLargeError(
            f"File exceeds maximum upload size of {MAX_BUNDLE_SIZE // (1024 * 1024)}MB."
        )

    try:
        with tarfile.open(fileobj=io.BytesIO(file_data), mode="r:gz") as tar:
            extracted_files: dict[str, bytes] = {}
            bundle_files: list[BundleFile] = []
            total_extracted = 0

            for member in tar.getmembers():
                if not member.isfile():
                    continue

                safe_path = _sanitize_path(member.name)
                if safe_path is None:
                    continue

                # Per-file size guard (check declared size before reading)
                if member.size > MAX_SINGLE_FILE_SIZE:
                    continue

                file_obj = tar.extractfile(member)
                if file_obj is None:
                    continue

                content = file_obj.read(MAX_SINGLE_FILE_SIZE + 1)
                if len(content) > MAX_SINGLE_FILE_SIZE:
                    continue

                total_extracted += len(content)
                if total_extracted > MAX_EXTRACTED_SIZE:
                    raise BundleTooLargeError(
                        "Decompressed bundle content exceeds 2GB limit."
                    )

                if len(extracted_files) >= MAX_FILE_COUNT:
                    break

                extracted_files[safe_path] = content
                bundle_files.append(
                    BundleFile(
                        path=safe_path,
                        size_bytes=len(content),
                        signal_type=SignalType.other,
                    )
                )

            total_size = sum(len(v) for v in extracted_files.values())
            manifest = BundleManifest(
                total_files=len(bundle_files),
                total_size_bytes=total_size,
                files=bundle_files,
            )
            return manifest, extracted_files

    except tarfile.TarError as e:
        raise InvalidBundleError("Invalid file format. Expected a .tar.gz archive.") from e


def _sanitize_path(path: str) -> str | None:
    """Sanitize a tar member path to prevent path traversal.

    Uses posixpath for deterministic behavior regardless of host OS.
    """
    if ".." in path.split("/"):
        return None

    normalized = posixpath.normpath(path)

    if normalized.startswith("..") or normalized.startswith("/"):
        return None

    if ".." in normalized.split("/"):
        return None

    return normalized
