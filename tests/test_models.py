import csv
import json
import logging
import os

import pytest
from asnake.client import ASnakeClient

from asaps import models


@pytest.fixture
def as_ops():
    client = ASnakeClient(
        baseurl="mock://example.com", username="test", password="test"
    )
    as_ops = models.AsOperations(client)
    return as_ops


def test_get_all_records(as_ops):
    """Test get_all_records method."""
    endpoint = "/repositories/0/resources"
    ids = as_ops.get_all_records(endpoint)
    assert ids == [423, 756]


def test_get_archival_objects_for_resource(as_ops):
    """Test get_archival_objects_for_resource method."""
    resource = "/repositories/0/resources/423"
    arch_obj_list = as_ops.get_archival_objects_for_resource(resource)
    assert "/repositories/0/archival_objects/1234" in arch_obj_list


def test_get_record(as_ops):
    """Test get_record method."""
    uri = "/repositories/0/resources/423"
    response = as_ops.get_record(uri)
    assert response["jsonmodel_type"] == "resource"


def test_post_new_record(as_ops):
    """Test post_new_record method."""
    endpoint = "/repositories/0/resources"
    rec_obj = {"title": "Test title"}
    resp = as_ops.post_new_record(rec_obj, endpoint)
    assert resp["status"] == "Created"


def test_save_record(as_ops, caplog):
    """Test post_record method."""
    caplog.set_level(logging.INFO)
    rec_obj = models.Record()
    uri = "/repositories/0/resources/423"
    dry_run = "False"
    rec_obj["uri"] = uri
    as_ops.save_record(rec_obj, dry_run)
    message = json.loads(caplog.messages[0])["event"]
    assert message == {"post": "Success"}


def test_search(as_ops):
    """Test search method."""
    string = "string"
    repo_id = "0"
    rec_type = "resource"
    field = "acqinfo"
    results = as_ops.search(string, repo_id, rec_type, field)
    for result in results:
        assert result == "/repositories/0/archival_objects/1234"


def test_record_is_modified():
    """Test record_is_modified method."""
    record = models.Record()
    assert not record.modified
    record["title"] = "I am different"
    assert record.modified


def test_record_flush_persists_changes():
    """Test record_flush_persists_changes method."""
    record = models.Record()
    record["title"] = "I am a title"
    assert record.modified
    record.flush()
    assert not record.modified


def test_changes_returns_json_patch_operations():
    """Test changes_returns_json_patch_operations method."""
    record = models.Record()
    record["title"] = "I am a title"
    assert record.changes == [{"op": "add", "path": "/title", "value": "I am a title"}]


def test_save_record_flushes_changes(as_ops):
    """Test save_record_flushes_changes method."""
    uri = "/repositories/0/resources/423"
    dry_run = "False"
    r = models.Record({"uri": uri})
    r["title"] = "A title"
    assert r.modified
    as_ops.save_record(r, dry_run)
    assert not r.modified


def test_audit():
    """ "Test audit function."""
    sample_record = {"uri": "123"}
    change = {"op": "add", "path": "/title", "value": "I am a title"}
    msg = models.audit(record=sample_record, **change)
    assert msg == {"uri": "123", "field": "/title", "old": None, "new": "I am a title"}


def test_concat_id():
    """ "Test concat_id function."""
    rec_obj = {"id_0": "1", "id_1": "2", "id_2": "3", "id_3": "4"}
    coll_id = models.concat_id(rec_obj)
    assert coll_id == "1-2-3-4"


def test_create_endpoint():
    """Test create_endpoint method."""
    rec_type = "resource"
    repo_id = "0"
    endpoint = models.create_endpoint(rec_type, repo_id)
    assert endpoint == "repositories/0/resources"


def test_create_csv_from_log(runner):
    """ "Test create_csv_from_log function."""
    with runner.isolated_filesystem():
        os.mkdir("logs")
        with open("logs/log-1790-01-01.log", "w") as log_file:
            log_data = json.dumps(
                {
                    "uri": "/repositories/0/events/123",
                    "event_type": "processed",
                    "date": "1861-04-10",
                    "logger": "asaps.cli",
                    "level": "info",
                    "timestamp": "2021-03-04T15:21:28.616824Z",
                }
            )
            log_file.write(log_data)
        models.create_csv_from_log("test-", "1790-01-01.log", True)
        with open("test-1790-01-01.log.csv") as csvfile2:
            reader = csv.DictReader(csvfile2)
            for row in reader:
                assert row["uri"] == "/repositories/0/events/123"
                assert row["event_type"] == "processed"
                assert row["date"] == "1861-04-10"


def test_download_json():
    """Test download_json function."""
    rec_obj = models.Record()
    rec_obj["uri"] = "/test/123"
    path = models.download_json(rec_obj)
    assert os.path.isfile(path)
    os.remove(path)


def test_extract_note_field():
    """ "Test extract_note_field function."""
    field = "acqinfo"
    rec_obj = {"notes": [{"type": "acqinfo", "subnotes": [{"content": "test value"}]}]}
    report_dict = {"uri": "123", "title": "Title", "id": "456"}
    report_dicts = models.extract_note_field(field, rec_obj, report_dict)
    for report_dict in report_dicts:
        assert report_dict["uri"] == "123"
        assert report_dict["acqinfo"] == "test value"


def test_extract_obj_field():
    """ "Test extract_obj_field function."""
    field = "dates"
    rec_obj = {"dates": [{"begin": "1900", "end": "1901", "date_type": "inclusive"}]}
    report_dict = {"uri": "123", "title": "Title", "id": "456"}
    obj_field_dict = {"dates": ["begin", "end", "expression", "label", "date_type"]}
    report_dicts = models.extract_obj_field(field, rec_obj, obj_field_dict, report_dict)
    for report_dict in report_dicts:
        assert report_dict["uri"] == "123"
        assert report_dict["begin"] == "1900"
        assert report_dict["end"] == "1901"
        assert report_dict["date_type"] == "inclusive"


def test_filter_note_type():
    """Test filter_note_type function."""
    rec_obj = {"notes": [{"note_type": "acqinfo"}, {"note_type": "bioghist"}]}
    notes = models.filter_note_type(rec_obj, "acqinfo")
    for note in notes:
        assert note["note_type"] == "acqinfo"


def test_string_to_uri():
    agent_links = []
    string = "Smith, N."
    uri_dict = {"Smith, N.": "mock.mock/123"}
    role = "creator"
    agent_links = models.string_to_uri(agent_links, string, uri_dict, role, "")
    assert agent_links[0]["ref"] == uri_dict[string]
    assert agent_links[0]["role"] == role
