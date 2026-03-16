"""Bundle parser — validates and extracts .tar.gz support bundles in memory."""

import io
import os
import tarfile

from app.models.schemas import BundleFile, BundleManifest, SignalType

MAX_BUNDLE_SIZE = 500 * 1024 * 1024  # 500MB


class InvalidBundleError(Exception):
    """Raised when the uploaded file is not a valid .tar.gz archive."""


class BundleTooLargeError(Exception):
    """Raised when the uploaded file exceeds the maximum size limit."""


def parse_bundle(file_data: bytes) -> tuple[BundleManifest, dict[str, bytes]]:
    """Parse a .tar.gz bundle, extract contents in memory, and return manifest + files.

    Args:
        file_data: Raw bytes of the uploaded file.

    Returns:
        Tuple of (BundleManifest, dict mapping file paths to their contents).

    Raises:
        BundleTooLargeError: If file exceeds 500MB.
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

            for member in tar.getmembers():
                if not member.isfile():
                    continue

                safe_path = _sanitize_path(member.name)
                if safe_path is None:
                    continue

                file_obj = tar.extractfile(member)
                if file_obj is None:
                    continue

                content = file_obj.read()
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

    Returns None if the path is unsafe and should be skipped.
    A path is considered unsafe if:
    - It contains '..' components (before or after normalization)
    - It starts with '/' (absolute path)
    - Normalization changes the path's top-level directory (traversal escape)
    """
    if ".." in path.split("/"):
        return None

    normalized = os.path.normpath(path)

    if normalized.startswith("..") or normalized.startswith("/"):
        return None

    if ".." in normalized.split(os.sep):
        return None

    return normalized
