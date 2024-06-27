import operator

filter_crit = operator.itemgetter(1)


def create_agent_pers(
    agent_type,
    primary_name,
    sort_name,
    rest_of_name,
    fuller_form,
    title,
    prefix,
    suffix,
    dates,
    expression,
    begin,
    end,
    authority_id,
    certainty,
    label,
):
    """Create agent_person record."""
    agent = {}
    name = {}
    name["primary_name"] = primary_name
    name["name_order"] = "inverted"
    name["jsonmodel_type"] = "name_person"
    name["rules"] = "rda"
    name["sort_name"] = sort_name
    name["authority_id"] = authority_id
    name["source"] = "Virtual International Authority File (VIAF)"
    name["rest_of_name"] = rest_of_name
    name["fuller_form"] = fuller_form
    name["title"] = title
    name["prefix"] = prefix
    name["suffix"] = suffix
    name["dates"] = dates
    name = dict(filter(filter_crit, name.items()))
    if "authority_id" not in name:
        name["rules"] = "dacs"
        name["source"] = "local"
    if "rest_of_name" not in name:
        name["name_order"] = "direct"
    names = [name]
    date = create_date(begin, end, expression, certainty, label)
    agent["dates_of_existence"] = [date]
    agent["names"] = names
    agent["publish"] = True
    agent["jsonmodel_type"] = agent_type
    return agent


def create_agent_corp(
    agent_type,
    primary_name,
    sort_name,
    subordinate_name_1,
    subordinate_name_2,
    number,
    dates,
    qualifier,
    authority_id,
):
    """Create agent_corporate_entity record."""
    agent = {}
    name = {}
    name["primary_name"] = primary_name
    name["name_order"] = "direct"
    name["jsonmodel_type"] = "name_corporate_entity"
    name["rules"] = "rda"
    name["sort_name"] = sort_name
    name["authority_id"] = authority_id
    name["source"] = "Virtual International Authority File (VIAF)"
    name["subordinate_name_1"] = subordinate_name_1
    name["subordinate_name_2"] = subordinate_name_2
    name["number"] = number
    name["dates"] = dates
    name["qualifer"] = qualifier
    name = dict(filter(filter_crit, name.items()))
    if "authority_id" not in name:
        name["rules"] = "dacs"
        name["source"] = "local"
    names = [name]
    agent["names"] = names
    agent["publish"] = True
    agent["jsonmodel_type"] = agent_type
    return agent


def create_arch_obj(
    title,
    level,
    agents,
    notes,
    parent,
    resource,
    begin,
    end,
    expression,
    certainty,
    label,
):
    """Create archival object."""
    arch_obj = {}
    arch_obj["title"] = title
    arch_obj["level"] = level
    arch_obj["linked_agents"] = agents
    arch_obj["notes"] = notes
    arch_obj["publish"] = True
    arch_obj["parent"] = {"ref": parent}
    arch_obj["resource"] = {"ref": resource}
    arch_obj["instances"] = []
    date = create_date(begin, end, expression, certainty, label)
    arch_obj["dates"] = [date]
    return arch_obj


def create_date(begin, end, expression, certainty, label):
    """Create date object."""
    date = {}
    date["begin"] = begin
    date["end"] = end
    date["expression"] = expression
    date["certainty"] = certainty
    date = dict(filter(filter_crit, date.items()))
    if "begin" in date and "end" in date:
        date["date_type"] = "range"
    elif "begin" in date:
        date["date_type"] = "single"
    elif "end" in date:
        date["date_type"] = "single"
    elif "expression" in date:
        date["date_type"] = "single"
    if len(date) > 0:
        date["label"] = label
        date["jsonmodel_type"] = "date"
    return date


def create_dig_obj(title, link):
    """Create digital object."""
    dig_obj = {}
    dig_obj["title"] = title
    dig_obj["publish"] = True
    dig_obj["file_versions"] = []
    dig_obj = update_dig_obj_link(dig_obj, link)
    return dig_obj


def create_note(type, label, content):
    """Create note object."""
    note = {}
    note["jsonmodel_type"] = "note_multipart"
    note["type"] = type
    note["label"] = label
    note["publish"] = True
    subnote = {}
    subnote["publish"] = True
    subnote["content"] = content
    subnote["jsonmodel_type"] = "note_text"
    note["subnotes"] = [subnote]
    return note


def link_dig_obj(arch_obj, dig_obj_uri):
    """Link digital object to archival object."""
    instance = {}
    instance["instance_type"] = "digital_object"
    instance["jsonmodel_type"] = "instance"
    instance["digital_object"] = {"ref": dig_obj_uri}
    instance["is_representative"] = False
    arch_obj["instances"].append(instance)
    return arch_obj


def link_top_container(arch_obj, top_cont_uri, child_type, child_indicator):
    """Link top container to archival object."""
    instance = {}
    instance["instance_type"] = "mixed_materials"
    instance["jsonmodel_type"] = "instance"
    instance["indicator_2"] = child_indicator
    instance["type_2"] = child_type
    sub_container = {}
    sub_container["indicator_2"] = child_indicator
    sub_container["type_2"] = child_type
    sub_container["jsonmodel_type"] = "sub_container"
    sub_container["top_container"] = {"ref": top_cont_uri}
    instance["sub_container"] = sub_container
    instance["is_representative"] = False
    arch_obj["instances"].append(instance)
    return arch_obj


def update_dig_obj_link(dig_obj, link):
    """Get digital objects associated with an archival objects."""
    dig_obj["digital_object_id"] = link
    if len(dig_obj["file_versions"]) != 0:
        for file_version in dig_obj["file_versions"]:
            file_version["file_uri"] = link
    else:
        file_version = {}
        file_version["file_uri"] = link
        file_version["publish"] = True
        file_version["is_representative"] = False
        file_version["jsonmodel_type"] = "file_version"
        dig_obj["file_versions"] = [file_version]
        file_version["xlink_actuate_attribute"] = "onRequest"
        file_version["xlink_show_attribute"] = "new"
    return dig_obj
