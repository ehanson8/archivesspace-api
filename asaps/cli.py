import csv
import datetime
import json
import logging
import os
import time

import click
import structlog
from asnake.client import ASnakeClient

from asaps import models, records, workflows

logger = structlog.get_logger()


note_type_fields = [
    "abstract",
    "accessrestrict",
    "acqinfo",
    "altformavail",
    "appraisal",
    "arrangement",
    "bibliography",
    "bioghist",
    "custodhist",
    "prefercite",
    "processinfo",
    "relatedmaterial",
    "scopecontent",
    "userestrict",
]
obj_field_dict = {
    "dates": ["begin", "end", "expression", "label", "date_type"],
    "extents": [
        "portion",
        "number",
        "extent_type",
        "container_summary",
        "physical_details",
        "dimensions",
    ],
}

skipped_resources = []


@click.group()
@click.option("--url", envvar="AS_BASEURL")
@click.option(
    "-u",
    "--username",
    prompt="Enter username",
    envvar="AS_USERNAME",
    help="The username for authentication.",
)
@click.option(
    "-p",
    "--password",
    prompt="Enter password",
    hide_input=True,
    envvar="AS_PASSWORD",
    help="The password for authentication.",
)
@click.pass_context
def main(ctx, url, username, password):
    ctx.obj = {}
    if os.path.isdir("logs") is False:
        os.mkdir("logs")
    dt = datetime.datetime.utcnow().isoformat(timespec="seconds")
    log_suffix = f"{dt}.log"
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(
        format="%(message)s",
        handlers=[logging.FileHandler(f"logs/log-{log_suffix}", "w")],
        level=logging.INFO,
    )
    logger.info("Application start")

    client = ASnakeClient(baseurl=url, username=username, password=password)
    as_ops = models.AsOperations(client)
    start_time = time.time()
    ctx.obj["as_ops"] = as_ops
    ctx.obj["start_time"] = start_time
    ctx.obj["log_suffix"] = log_suffix


@main.command()
@click.pass_context
@click.option(
    "-d",
    "--dry_run",
    prompt="Dry run?",
    default=True,
    help="Perform dry run that does not modify any records.",
)
@click.option(
    "-m",
    "--metadata_csv",
    prompt="Enter the metadata CSV file",
    help="The metadata CSV file to use.",
)
@click.option("-f", "--field", prompt="Enter the field", help="The field to edit.")
def deletefield(ctx, dry_run, metadata_csv, field):
    """Deletes the specified field from records that are specified in a CSV
    file."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            uri = row["uri"]
            rec_obj = as_ops.get_record(uri)
            if field in note_type_fields:
                for note in (n for n in rec_obj["notes"] if n.get("type") == field):
                    rec_obj["notes"].remove(note)
            else:
                rec_obj.pop(field, None)
            if rec_obj.modified is True:
                as_ops.save_record(rec_obj, dry_run)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log(f"update_rec_{field}", log_suffix)


@main.command()
@click.pass_context
@click.argument("search")
@click.option(
    "-d",
    "--dry_run",
    prompt="Dry run?",
    default=True,
    help="Perform dry run that does not modify any records.",
)
@click.option(
    "-i",
    "--repo_id",
    prompt="Enter the repository ID",
    help="The ID of the repository to use.",
)
@click.option(
    "-t", "--rec_type", prompt="Enter the record type", help="The record type to use."
)
@click.option("-f", "--field", prompt="Enter the field", help="The field to edit.")
@click.option(
    "-r",
    "--rpl_value",
    prompt="Enter the replacement value",
    help="The replacement value to be inserted.",
)
def find(ctx, dry_run, repo_id, rec_type, field, search, rpl_value):
    """Finds and replaces the specified string in the specified field in all
    records of the specified type of records"""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    skipped_arch_objs = []
    if rec_type == "archival_object":
        for uri in skipped_resources:
            arch_obj_list = as_ops.get_archival_objects_for_resource(uri)
            skipped_arch_objs.append(arch_obj_list)
    skipped_uris = skipped_resources + skipped_arch_objs
    for uri in as_ops.search(search, repo_id, rec_type, field):
        if uri not in skipped_uris:
            rec_obj = as_ops.get_record(uri)
            if field in note_type_fields:
                notes = models.filter_note_type(rec_obj, field)
                for note in notes:
                    for subnote in note.get("subnotes", []):
                        if "content" in subnote:
                            update = subnote["content"].replace(search, rpl_value)
                            subnote["content"] = update
                        elif "definedlist" in subnote:
                            update = subnote["definedlist"].replace(search, rpl_value)
                            subnote["definedlist"] = update
            else:
                update = rec_obj.get(field, "").replace(search, rpl_value)
                rec_obj[field] = update
            if rec_obj.modified is True:
                as_ops.save_record(rec_obj, dry_run)
        else:
            logger.info(f"{uri} skipped")
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log(f"{rec_type}-{field}-find", log_suffix)


@main.command()
@click.pass_context
@click.option("-r", "--resource", prompt="Enter the resource number")
@click.option(
    "-i",
    "--file_identifier",
    prompt="Enter the field for file matching",
    help="The field for file matching.",
)
@click.option(
    "-e",
    "--repo_id",
    prompt="Enter the repository ID",
    help="The ID of the repository to use.",
)
def metadata(ctx, resource, file_identifier, repo_id):
    """Exports metadata from a resource's archival objects that will be matched
    to files in preparation for ingesting the files into a repository."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    report_dicts = workflows.export_metadata(as_ops, resource, file_identifier, repo_id)
    for report_dict in report_dicts:
        logger.info(**report_dict)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log(resource, log_suffix, False)


@main.command()
@click.pass_context
@click.option(
    "-m",
    "--metadata_csv",
    prompt="Enter the metadata CSV file",
    help="The metadata CSV file to use.",
)
@click.option(
    "-o",
    "--output_path",
    prompt="Enter the output path",
    default="",
    help="The path of the output files, include " "/ at the end of the path",
)
@click.option(
    "-p",
    "--match_point",
    prompt="Enter the match point",
    help="The match point to be used in the new record report.",
)
def newagents(ctx, metadata_csv, output_path, match_point):
    """Creates new agent records based on a CSV file."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        new_rec_data = {}
        for row in reader:
            agent_type = row["agent_type"]
            if agent_type == "people":
                agent_rec = records.create_agent_pers(
                    agent_type,
                    row["primary_name"],
                    row["sort_name"],
                    row["rest_of_name"],
                    row["fuller_form"],
                    row["title"],
                    row["prefix"],
                    row["suffix"],
                    row["dates"],
                    row["expression"],
                    row["begin"],
                    row["end"],
                    row["authority_id"],
                    row["certainty"],
                    row["label"],
                )
            if agent_type == "corporate_entities":
                agent_rec = records.create_agent_corp(
                    agent_type,
                    row["primary_name"],
                    row["sort_name"],
                    row["subord_name_1"],
                    row["subord_name_2"],
                    row["number"],
                    row["dates"],
                    row["qualifier"],
                    row["authority_id"],
                )
            agent_endpoint = models.create_endpoint(agent_type)
            agent_resp = as_ops.post_new_record(agent_rec, agent_endpoint)
            new_rec_data[row[match_point]] = agent_resp["uri"]
        models.create_new_rec_report(new_rec_data, f"{output_path}newagents")
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log("agents", log_suffix)


@main.command()
@click.pass_context
@click.option(
    "-m",
    "--metadata_csv",
    prompt="Enter the metadata CSV file",
    help="The metadata CSV file to use.",
)
@click.option(
    "-a",
    "--agent_file",
    prompt="Enter the agent CSV file",
    help="The CSV mapping agent strings to URIs.",
)
@click.option(
    "-i",
    "--repo_id",
    prompt="Enter the repository ID",
    help="The ID of the repository to use.",
)
def newarchobjs(ctx, metadata_csv, agent_file, repo_id):
    """Creates new archival object records based on a CSV file."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    agent_uri_dict = {}
    with open(agent_file) as agentfile:
        reader = csv.DictReader(agentfile)
        for row in reader:
            agent_uri_dict[row["match_point"]] = row["uri"]
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            agent_links = []
            agent_links = models.string_to_uri(
                agent_links, row["publisher"], agent_uri_dict, "creator", "pbl"
            )
            for author in json.loads(row["authors"]):
                agent_links = models.string_to_uri(
                    agent_links, author, agent_uri_dict, "creator", ""
                )
            new_dig_obj = records.create_dig_obj(row["title"], row["link"])
            dig_obj_endpoint = models.create_endpoint("digital_object", repo_id)
            dig_obj_resp = as_ops.post_new_record(new_dig_obj, dig_obj_endpoint)
            note = records.create_note(
                "scopecontent", "Scope and Contents", row["abstract"]
            )
            arch_obj = records.create_arch_obj(
                row["title"],
                "file",
                agent_links,
                [note],
                row["parent_uri"],
                row["resource"],
                row["begin"],
                row["end"],
                row["expression"],
                row["certainty"],
                row["label"],
            )
            arch_obj = records.link_dig_obj(arch_obj, dig_obj_resp["uri"])
            arch_obj = records.link_top_container(
                arch_obj,
                row["top_container_1"],
                row["child_type"],
                row["child_indicator"],
            )
            arch_obj = records.link_top_container(
                arch_obj, row["top_container_2"], "", ""
            )
            arch_obj_endpoint = models.create_endpoint("archival_object", repo_id)
            as_ops.post_new_record(arch_obj, arch_obj_endpoint)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log("arch_obj", log_suffix)


@main.command()
@click.pass_context
@click.option(
    "-m",
    "--metadata_csv",
    prompt="Enter the metadata CSV file",
    help="The metadata CSV file to use.",
)
@click.option(
    "-i",
    "--repo_id",
    prompt="Enter the repository ID",
    help="The ID of the repository to use.",
)
def newdigobjs(ctx, metadata_csv, repo_id):
    """Creates new digital object records based on a CSV file."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    workflows.create_new_dig_objs(as_ops, metadata_csv, repo_id)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log("new_dig_obj", log_suffix)


@main.command()
@click.option(
    "-i",
    "--repo_id",
    prompt="Enter the repository ID",
    help="The ID of the repository to use.",
)
@click.option(
    "-t", "--rec_type", prompt="Enter the record type", help="The record type to use."
)
@click.option("-f", "--field", prompt="Enter the field", help="The field to extract.")
@click.pass_context
def report(ctx, repo_id, rec_type, field):
    """Exports a report containing minimal metadata and a specified field from
    all records of the specified type."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    endpoint = models.create_endpoint(rec_type, repo_id)
    ids = as_ops.get_all_records(endpoint)
    for id in ids:
        uri = f"{endpoint}/{id}"
        rec_obj = as_ops.get_record(uri)
        coll_id = models.concat_id(rec_obj)
        report_dict = {"uri": rec_obj["uri"], "title": rec_obj["title"], "id": coll_id}
        if field in note_type_fields:
            report_dicts = models.extract_note_field(field, rec_obj, report_dict)
            for report_dict in report_dicts:
                logger.info(**report_dict)
        elif field in obj_field_dict:
            report_dicts = models.extract_obj_field(
                field, rec_obj, obj_field_dict, report_dict
            )
            for report_dict in report_dicts:
                logger.info(**report_dict)
        else:
            report_dict[field] = rec_obj.get(field, "")
            logger.info(**report_dict)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log(f"{rec_type}-{field}-values", log_suffix)


@main.command()
@click.pass_context
@click.option(
    "-d",
    "--dry_run",
    prompt="Dry run?",
    default=True,
    help="Perform dry run that does not modify any records.",
)
@click.option(
    "-m",
    "--metadata_csv",
    prompt="Enter the metadata CSV file",
    help="The metadata CSV file to use.",
)
def updatedigobj(ctx, dry_run, metadata_csv):
    """Updates the link in digital objects listed in a CSV file."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            do_uri = row["do_uri"]
            link = row["link"]
            dig_obj = as_ops.get_record(do_uri)
            upd_dig_obj = records.update_dig_obj_link(dig_obj, link)
            if upd_dig_obj.modified is True:
                as_ops.save_record(upd_dig_obj, dry_run)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log("dig_obj", log_suffix)


@main.command()
@click.pass_context
@click.option(
    "-d",
    "--dry_run",
    prompt="Dry run?",
    default=True,
    help="Perform dry run that does not modify any records.",
)
@click.option(
    "-m",
    "--metadata_csv",
    prompt="Enter the metadata CSV file",
    help="The metadata CSV file to use.",
)
@click.option("-f", "--field", prompt="Enter the field", help="The field to edit.")
@click.option(
    "-r",
    "--rpl_value_col",
    prompt="Enter the replacement value column",
    help="The replacement value to be inserted.",
)
def updaterecords(ctx, dry_run, metadata_csv, field, rpl_value_col):
    """Updates records with values listed in a CSV file."""
    as_ops = ctx.obj["as_ops"]
    start_time = ctx.obj["start_time"]
    log_suffix = ctx.obj["log_suffix"]
    with open(metadata_csv) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            uri = row["uri"]
            rpl_value = row[rpl_value_col]
            rec_obj = as_ops.get_record(uri)
            if field in note_type_fields:
                notes = models.filter_note_type(rec_obj, field)
                note_found = False
                for note in notes:
                    for subnote in note.get("subnotes", []):
                        subnote["content"] = rpl_value
                        note_found = True
                if note_found is not True:
                    note = {}
                    note["jsonmodel_type"] = "note_multipart"
                    note["type"] = field
                    note["publish"] = True
                    note["subnotes"] = [
                        {
                            "jsonmodel_type": "note_text",
                            "content": rpl_value,
                            "publish": True,
                        }
                    ]
                    rec_obj["notes"].append(note)
            else:
                rec_obj[field] = rpl_value
            if rec_obj.modified is True:
                as_ops.save_record(rec_obj, dry_run)
    models.elapsed_time(start_time, "Total runtime:")
    models.create_csv_from_log(f"update_rec_{field}", log_suffix)
