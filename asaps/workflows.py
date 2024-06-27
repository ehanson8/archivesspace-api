import csv

from asaps import models, records


def export_metadata(client, resource, file_identifier, repo_id):
    """Export ArchivesSpace metadata as dicts for each archival object."""
    resource_uri = f"/repositories/{repo_id}/resources/{resource}"
    archival_object_list = client.get_archival_objects_for_resource(resource_uri)
    for uri in archival_object_list:
        record_object = client.get_record(uri)
        if file_identifier == "uri":
            repo_id = record_object["uri"].replace("/repositories/", "")
            repo_id = repo_id[: repo_id.index("/archival_objects/")]
            rec_id_split = record_object["uri"].rindex("/archival_objects/")
            rec_id = record_object["uri"][rec_id_split + 18 :]
            file_identifier_value = f"{repo_id.zfill(2)}-{rec_id.zfill(9)}"
        else:
            file_identifier_value = record_object.get(file_identifier)
        report_dict = {
            "uri": record_object["uri"],
            "title": record_object["display_string"],
            "file_identifier": file_identifier_value,
        }
        yield report_dict


def create_new_dig_objs(client, metadata_csv, repo_id):
    """Creates new digital objects based on a CSV."""
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            uri = row["uri"]
            arch_obj = client.get_record(uri)
            new_dig_obj = records.create_dig_obj(
                arch_obj["display_string"], row["link"]
            )
            dig_obj_endpoint = models.create_endpoint("digital_object", repo_id)
            dig_obj_resp = client.post_new_record(new_dig_obj, dig_obj_endpoint)
            arch_obj = records.link_dig_obj(arch_obj, dig_obj_resp["uri"])
            client.save_record(arch_obj, "False")
