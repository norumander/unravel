"""Unit tests for bundle parser."""

import io
import tarfile

import pytest

from app.bundle.parser import (
    BundleTooLargeError,
    InvalidBundleError,
    parse_bundle,
)


def _make_tar_gz(files: dict[str, bytes]) -> bytes:
    """Create an in-memory .tar.gz archive from a dict of path -> content."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestParseBundle:
    def test_valid_bundle_returns_manifest_and_files(self):
        files = {
            "bundle/logs/pod.log": b"log line 1\nlog line 2",
            "bundle/cluster-info/nodes.json": b'{"nodes": []}',
        }
        tar_data = _make_tar_gz(files)
        manifest, extracted = parse_bundle(tar_data)

        assert manifest.total_files == 2
        assert manifest.total_size_bytes == len(b"log line 1\nlog line 2") + len(
            b'{"nodes": []}'
        )
        assert len(extracted) == 2
        assert b"log line 1" in extracted["bundle/logs/pod.log"]

    def test_manifest_file_paths_match(self):
        files = {"a/b/c.txt": b"hello"}
        tar_data = _make_tar_gz(files)
        manifest, _ = parse_bundle(tar_data)

        assert manifest.files[0].path == "a/b/c.txt"
        assert manifest.files[0].size_bytes == 5

    def test_empty_archive_returns_empty_manifest(self):
        tar_data = _make_tar_gz({})
        manifest, extracted = parse_bundle(tar_data)

        assert manifest.total_files == 0
        assert manifest.total_size_bytes == 0
        assert len(extracted) == 0

    def test_nested_directories_extracted(self):
        files = {
            "bundle/deep/nested/dir/file.txt": b"deep content",
        }
        tar_data = _make_tar_gz(files)
        manifest, extracted = parse_bundle(tar_data)

        assert manifest.total_files == 1
        assert "bundle/deep/nested/dir/file.txt" in extracted

    def test_directories_not_included_in_manifest(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # Add a directory entry
            dir_info = tarfile.TarInfo(name="bundle/logs/")
            dir_info.type = tarfile.DIRTYPE
            tar.addfile(dir_info)
            # Add a file entry
            file_data = b"log content"
            file_info = tarfile.TarInfo(name="bundle/logs/pod.log")
            file_info.size = len(file_data)
            tar.addfile(file_info, io.BytesIO(file_data))

        manifest, extracted = parse_bundle(buf.getvalue())
        assert manifest.total_files == 1
        assert len(extracted) == 1


class TestInvalidBundle:
    def test_non_tar_gz_raises_error(self):
        with pytest.raises(InvalidBundleError, match="Invalid file format"):
            parse_bundle(b"this is not a tar.gz file")

    def test_plain_text_raises_error(self):
        with pytest.raises(InvalidBundleError):
            parse_bundle(b"hello world")

    def test_zip_file_raises_error(self):
        # Minimal ZIP header
        with pytest.raises(InvalidBundleError):
            parse_bundle(b"PK\x03\x04" + b"\x00" * 100)


class TestBundleTooLarge:
    def test_oversized_file_raises_error(self):
        # Create data just over the limit (we only check len, not actual tar content)
        oversized = b"x" * (500 * 1024 * 1024 + 1)
        with pytest.raises(BundleTooLargeError, match="500MB"):
            parse_bundle(oversized)

    def test_exactly_at_limit_does_not_raise(self):
        # At exactly the limit, it should not raise BundleTooLargeError
        # (it will raise InvalidBundleError because it's not valid tar.gz)
        at_limit = b"x" * (500 * 1024 * 1024)
        with pytest.raises(InvalidBundleError):
            parse_bundle(at_limit)


class TestPathTraversal:
    def test_traversal_path_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # Malicious path
            evil_data = b"evil content"
            evil_info = tarfile.TarInfo(name="../../etc/passwd")
            evil_info.size = len(evil_data)
            tar.addfile(evil_info, io.BytesIO(evil_data))
            # Safe path
            safe_data = b"safe content"
            safe_info = tarfile.TarInfo(name="bundle/safe.txt")
            safe_info.size = len(safe_data)
            tar.addfile(safe_info, io.BytesIO(safe_data))

        manifest, extracted = parse_bundle(buf.getvalue())
        assert manifest.total_files == 1
        assert "bundle/safe.txt" in extracted
        assert "../../etc/passwd" not in extracted

    def test_absolute_path_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"content"
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        manifest, extracted = parse_bundle(buf.getvalue())
        assert manifest.total_files == 0
        assert len(extracted) == 0

    def test_mid_path_traversal_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"content"
            info = tarfile.TarInfo(name="bundle/logs/../../etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        manifest, extracted = parse_bundle(buf.getvalue())
        assert manifest.total_files == 0
        assert len(extracted) == 0
