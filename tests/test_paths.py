from pathlib import Path

from mmco import paths


def test_session_dir_is_recordings_slash_session_id():
    base = Path("/data")
    assert paths.session_dir(base, "sess-001") == Path("/data/recordings/sess-001")


def test_session_artifact_paths_use_canonical_filenames():
    base = Path("/data")
    sd = paths.session_dir(base, "sess-001")
    assert paths.manifest_path(sd) == sd / "manifest.json"
    assert paths.session_log_path(sd) == sd / "session.log.jsonl"
    assert paths.summary_path(sd) == sd / "summary.md"


def test_filename_constants_are_stable_strings():
    assert paths.RECORDINGS_DIRNAME == "recordings"
    assert paths.MANIFEST_FILENAME == "manifest.json"
    assert paths.SESSION_LOG_FILENAME == "session.log.jsonl"
    assert paths.SUMMARY_FILENAME == "summary.md"
