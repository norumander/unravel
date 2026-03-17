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
        manifest, extracted, _ = parse_bundle(tar_data)

        assert manifest.total_files == 2
        assert manifest.total_size_bytes == len(b"log line 1\nlog line 2") + len(
            b'{"nodes": []}'
        )
        assert len(extracted) == 2
        assert b"log line 1" in extracted["bundle/logs/pod.log"]

    def test_manifest_file_paths_match(self):
        files = {"a/b/c.txt": b"hello"}
        tar_data = _make_tar_gz(files)
        manifest, _, _ = parse_bundle(tar_data)

        assert manifest.files[0].path == "a/b/c.txt"
        assert manifest.files[0].size_bytes == 5

    def test_empty_archive_returns_empty_manifest(self):
        tar_data = _make_tar_gz({})
        manifest, extracted, _ = parse_bundle(tar_data)

        assert manifest.total_files == 0
        assert manifest.total_size_bytes == 0
        assert len(extracted) == 0

    def test_nested_directories_extracted(self):
        files = {
            "bundle/deep/nested/dir/file.txt": b"deep content",
        }
        tar_data = _make_tar_gz(files)
        manifest, extracted, _ = parse_bundle(tar_data)

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

        manifest, extracted, _ = parse_bundle(buf.getvalue())
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

        manifest, extracted, warnings = parse_bundle(buf.getvalue())
        assert manifest.total_files == 1
        assert "bundle/safe.txt" in extracted
        assert "../../etc/passwd" not in extracted
        assert any("unsafe path" in w for w in warnings)

    def test_absolute_path_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"content"
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        manifest, extracted, _ = parse_bundle(buf.getvalue())
        assert manifest.total_files == 0
        assert len(extracted) == 0

    def test_mid_path_traversal_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = b"content"
            info = tarfile.TarInfo(name="bundle/logs/../../etc/passwd")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        manifest, extracted, _ = parse_bundle(buf.getvalue())
        assert manifest.total_files == 0
        assert len(extracted) == 0


from unittest.mock import patch

from app.bundle.parser import MAX_SINGLE_FILE_SIZE


class TestSingleFileSizeLimit:
    def test_file_over_max_single_size_skipped_with_warning(self):
        """U-16: A file whose declared size exceeds MAX_SINGLE_FILE_SIZE is skipped."""
        # Patch the limit to a small value so we don't need real 100MB data.
        tar_data = _make_tar_gz({"bundle/huge.bin": b"x" * 20})

        with patch("app.bundle.parser.MAX_SINGLE_FILE_SIZE", 10):
            manifest, extracted, warnings = parse_bundle(tar_data)

        assert manifest.total_files == 0
        assert len(extracted) == 0
        assert any("exceeds" in w for w in warnings)

    def test_file_at_exactly_max_single_size_accepted(self):
        """A file whose declared size equals MAX_SINGLE_FILE_SIZE is accepted."""
        # With patched limit of 10, a 10-byte file should be accepted.
        tar_data = _make_tar_gz({"bundle/borderline.bin": b"x" * 10})

        with patch("app.bundle.parser.MAX_SINGLE_FILE_SIZE", 10):
            manifest, extracted, warnings = parse_bundle(tar_data)

        assert manifest.total_files == 1
        assert "bundle/borderline.bin" in extracted


class TestFileCountLimit:
    def test_stops_at_max_file_count_with_warning(self):
        """U-17: Extraction stops at MAX_FILE_COUNT and emits a warning."""
        # Patch MAX_FILE_COUNT to a small value so we don't need 10,001 files.
        files = {f"bundle/file{i}.txt": b"data" for i in range(5)}
        tar_data = _make_tar_gz(files)

        with patch("app.bundle.parser.MAX_FILE_COUNT", 3):
            manifest, extracted, warnings = parse_bundle(tar_data)

        assert manifest.total_files == 3
        assert len(extracted) == 3
        assert any("remaining files skipped" in w for w in warnings)


class TestDeclaredVsActualSize:
    def test_declared_size_smaller_than_actual_reads_declared_amount(self):
        """U-18: When declared size < actual content, only declared bytes are extracted."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            actual_data = b"0123456789"  # 10 bytes
            info = tarfile.TarInfo(name="bundle/partial.txt")
            info.size = 5  # declare only 5
            tar.addfile(info, io.BytesIO(actual_data))

        manifest, extracted, _ = parse_bundle(buf.getvalue())
        assert manifest.total_files == 1
        assert len(extracted["bundle/partial.txt"]) == 5


class TestParseWarnings:
    def test_no_warnings_for_clean_bundle(self):
        """A normal bundle produces no warnings."""
        files = {
            "bundle/app.log": b"all good",
            "bundle/config.yaml": b"key: value",
        }
        tar_data = _make_tar_gz(files)
        _, _, warnings = parse_bundle(tar_data)
        assert warnings == []

    def test_multiple_warnings_accumulated(self):
        """A bundle with both an unsafe path and an oversized file returns multiple warnings."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # 1) Unsafe traversal path
            evil_data = b"evil"
            evil_info = tarfile.TarInfo(name="../../etc/shadow")
            evil_info.size = len(evil_data)
            tar.addfile(evil_info, io.BytesIO(evil_data))

            # 2) Oversized file — actual data is 20 bytes, patched limit will be 10
            big_data = b"x" * 20
            big_info = tarfile.TarInfo(name="bundle/big.bin")
            big_info.size = len(big_data)
            tar.addfile(big_info, io.BytesIO(big_data))

            # 3) A normal file to confirm it still works
            ok_data = b"fine"
            ok_info = tarfile.TarInfo(name="bundle/ok.txt")
            ok_info.size = len(ok_data)
            tar.addfile(ok_info, io.BytesIO(ok_data))

        with patch("app.bundle.parser.MAX_SINGLE_FILE_SIZE", 10):
            manifest, extracted, warnings = parse_bundle(buf.getvalue())

        assert len(warnings) >= 2
        assert any("unsafe path" in w for w in warnings)
        assert any("exceeds" in w for w in warnings)
        # The normal file should still be extracted
        assert manifest.total_files == 1
        assert "bundle/ok.txt" in extracted
