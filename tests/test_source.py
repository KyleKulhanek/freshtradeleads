from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from freshtradeleads.importer import import_xlsx
from freshtradeleads.schema import source_fetches
from freshtradeleads.source import FetchAlreadyRunning, SourceValidationError, acquisition_lock, fetch_source, validate_xlsx


def copier(source):
    def copy(_url,target,timeout=300):
        shutil.copyfile(source,target)
        return {"status":200,"etag":None,"last_modified":None,"content_length":source.stat().st_size},source.stat().st_size
    return copy


def test_download_validation_rejects_fake_xlsx(tmp_path):
    fake=tmp_path/"fake.xlsx"; fake.write_text("<html>error</html>")
    with pytest.raises(SourceValidationError): validate_xlsx(fake,min_bytes=1,min_rows=1)


def test_same_hash_fetch_is_clean_noop(engine,workbook,tmp_path,monkeypatch):
    original=import_xlsx(engine,workbook)
    monkeypatch.setattr("freshtradeleads.source.discover_source_date",lambda _url: date(2026,9,2))
    monkeypatch.setattr("freshtradeleads.source._download",copier(workbook))
    result=fetch_source(engine,tmp_path/"raw",min_bytes=1,min_rows=1)
    assert result["status"]=="unchanged" and result["matching_import_id"]==original["import_id"]
    assert not list((tmp_path/"raw").glob("*.part.xlsx"))


def test_atomic_new_download_and_failed_download_cleanup(engine,workbook,tmp_path,monkeypatch):
    monkeypatch.setattr("freshtradeleads.source.discover_source_date",lambda _url: date(2026,9,2))
    monkeypatch.setattr("freshtradeleads.source._download",copier(workbook))
    result=fetch_source(engine,tmp_path/"raw",min_bytes=1,min_rows=1)
    assert result["status"]=="imported" and Path(result["saved_path"]).name=="2026-09-02_MasterLicenseData.xlsx"
    stable=Path(result["saved_path"]); before=stable.read_bytes()
    fake=tmp_path/"fake"; fake.write_text("not xlsx"); monkeypatch.setattr("freshtradeleads.source._download",copier(fake))
    with pytest.raises(SourceValidationError): fetch_source(engine,tmp_path/"raw",min_bytes=1,min_rows=1)
    assert stable.read_bytes()==before and not list((tmp_path/"raw").glob("*.part.xlsx"))


def test_lock_prevents_overlap(tmp_path):
    lock=tmp_path/"fetch.lock"
    with acquisition_lock(lock):
        with pytest.raises(FetchAlreadyRunning):
            with acquisition_lock(lock): pass
