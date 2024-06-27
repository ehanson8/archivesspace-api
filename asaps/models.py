import copy
import csv
import datetime
import json
import os
import time

import jsonpatch
import jsonpointer
import structlog

logger = structlog.get_logger()


class AsOperations:
    def __init__(self, client):
        """Create instance and import client as attribute."""
        self.client = client

    def get_all_records(self, endpoint):
        """Retrieve all records from a specified endpoint."""
        ids = self.client.get(f"{endpoint}?all_ids=true").json()
        return ids

    def get_archival_objects_for_resource(self, uri):
        """Get archival objects associated with a resource."""
        logger.info(f"Retrieving AOs for {uri}")
        ordered_records = self.client.get(f"{uri}/ordered_records").json()
        return [
            record["ref"] for record in ordered_records["uris"] if record["depth"] > 0
        ]

    def get_record(self, uri):
        """Retrieve an individual record."""
        record = self.client.get(uri).json()
        logger.info(uri)
        return Record(record)

    def post_new_record(self, rec_obj, endpoint):
        """Create new ArchivesSpace record with POST of JSON data."""
        response = self.client.post(endpoint, json=rec_obj)
        logger.info(response.json())
        response.raise_for_status()
        return response.json()

    def save_record(self, rec_obj, dry_run):
        """Update ArchivesSpace record with POST of JSON data."""
        if dry_run == "False":
            response = self.client.post(rec_obj["uri"], json=rec_obj)
            logger.info(response.json())
            response.raise_for_status()
        rec_obj.flush()

    def search(self, string, repo_id, rec_type, field="keyword"):
        """Search for a string across a particular record type."""
        endpoint = f"repositories/{repo_id}/search?"
        query = {
            "query": {"field": field, "value": string, "jsonmodel_type": "field_query"}
        }
        params = {"aq": json.dumps(query), "page_size": 100, "type[]": rec_type}
        uris = []
        for result in self.client.get_paged(endpoint, params=params):
            uri = result["uri"]
            uris.append(uri)
        logger.info(f"{len(uris)} search results processed")
        return uris


class Record(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__persisted = copy.deepcopy(self)

    def flush(self):
        for change in self.changes:
            logger.info(**audit(record=self.__persisted, **change))
        self.__persisted = copy.deepcopy(self)

    @property
    def changes(self):
        return list(jsonpatch.make_patch(self.__persisted, self))

    @property
    def modified(self):
        return bool(self.changes)


def audit(**kwargs):
    """Create audit message."""
    record = kwargs["record"]
    op = kwargs["op"]
    path = kwargs["path"]

    uri = record.get("uri")
    if op == "add":
        new = kwargs.get("value")
        msg = {"uri": uri, "field": path, "old": None, "new": new}
    elif op == "replace":
        old = jsonpointer.resolve_pointer(record, path)
        new = kwargs.get("value")
        msg = {"uri": uri, "field": path, "old": old, "new": new}
    elif op == "remove":
        old = jsonpointer.resolve_pointer(record, path)
        msg = {"uri": uri, "field": path, "old": old, "new": None}
    else:
        msg = {}
    return msg


def concat_id(rec_obj):
    """Retrieve URI and concatenated IDs for record."""
    ids = [rec_obj.get(f"id_{x}", "") for x in range(4)]
    return "-".join(filter(None, ids))


def create_csv_from_log(csv_file_name, log_suffix, include_suffix=True):
    """Create csv from log file."""
    with open(f"logs/log-{log_suffix}") as f:
        logs = f.read().splitlines()
        edit_log_lines = []
        for line in logs:
            line_dict = json.loads(line)
            if "uri" in line_dict.keys():
                line_dict.pop("logger")
                line_dict.pop("level")
                line_dict.pop("timestamp")
                edit_log_lines.append(line_dict)
    if include_suffix:
        full_file_name = os.path.abspath(f"{csv_file_name}{log_suffix}.csv")
    else:
        full_file_name = os.path.abspath(f"{csv_file_name}.csv")
    if len(edit_log_lines) > 0:
        with open(f"{full_file_name}", "w") as fp:
            header = list(edit_log_lines[0].keys())
            f = csv.DictWriter(fp, fieldnames=header)
            f.writeheader()
            for edit_log_line in edit_log_lines:
                f.writerow(edit_log_line)


def create_endpoint(rec_type, repo_id=""):
    """Create an endpoint for a specified type."""
    rec_type_dict = {
        "accession": "accessions",
        "resource": "resources",
        "archival_object": "archival_objects",
        "agent_corporate_entity": "corporate_entities",
        "agent_person": "people",
        "agent_family": "families",
        "digital_object": "digital_objects",
        "top_container": "top_containers",
    }
    agents = ["corporate_entities", "families", "people"]
    non_repo_types = ["locations", "subjects"]
    if rec_type in agents:
        endpoint = f"agents/{rec_type}"
    elif rec_type in non_repo_types:
        endpoint = rec_type
    else:
        endpoint = f"repositories/{repo_id}/{rec_type_dict[rec_type]}"
    return endpoint


def create_new_rec_report(new_rec_data, file_name):
    """Creates a report of match points and ArchivesSpace URIs."""
    with open(f"{file_name}.csv", "w") as writecsv:
        writer = csv.writer(writecsv)
        writer.writerow(["match_point"] + ["uri"])
        for match_point, uri in new_rec_data.items():
            writer.writerow([match_point] + [uri])


def download_json(rec_obj):
    """Download a JSON file."""
    uri = rec_obj["uri"]
    file_name = uri[1 : len(uri)].replace("/", "-")
    f = open(file_name + ".json", "w")
    json.dump(rec_obj, f)
    f.close()
    return f.name


def elapsed_time(start_time, label):
    """Calculate elapsed time."""
    td = datetime.timedelta(seconds=time.time() - start_time)
    logger.info(f"{label} : {td}")


def extract_note_field(field, rec_obj, report_dict):
    """Extract note field content."""
    notes = filter_note_type(rec_obj, field)
    report_dict[field] = ""
    for note in notes:
        for subnote in note.get("subnotes", []):
            report_dict[field] = subnote.get("content", "")
            yield report_dict


def extract_obj_field(field, rec_obj, obj_field_dict, report_dict):
    """Extract field content where the value is an object."""
    keys = obj_field_dict[field]
    object_list = rec_obj[field]
    for obj in object_list:
        for key in keys:
            report_dict[key] = obj.get(key, "")
        yield report_dict


def filter_note_type(rec_obj, note_type):
    """Filter notes by type."""
    return (n for n in rec_obj["notes"] if n.get("type") == note_type)


def string_to_uri(agent_links, string, uri_dict, role, relator=""):
    """Creates an agent link from a dict of URIs and labels."""
    uri_found = False
    for label, uri in uri_dict.items():
        if string == label:
            uri_found = True
            if role != "":
                agent_links.append({"role": role, "ref": uri, "relator": relator})
            else:
                agent_links.append({"role": "creator", "ref": uri})
    if uri_found is False:
        logger.info(f"URI not found for string: {string}")
    return agent_links
