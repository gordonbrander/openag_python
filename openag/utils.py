import os
import json
import click
from urlparse import urlparse
from openag.categories import SENSORS, ACTUATORS
from openag.db_names import FIRMWARE_MODULE_TYPE, FIRMWARE_MODULE
from openag.models import FirmwareModuleType, FirmwareModule

def synthesize_firmware_module_info(modules, module_types):
    """
    Modules are allowed to define attributes on their inputs and outputs that
    override the values defined in their respective module types. This function
    takes as input a dictionary of `modules` (mapping module IDs to
    :class:`~openag.models.FirmwareModule` objects) and a dictionary of
    `module_types` (mapping module type IDs to
    :class:`~openag.models.FirmwareModuleType` objects). For each module, it
    synthesizes the information in that module and the corresponding module
    type and returns all the results in a dictionary keyed on the ID of the
    module
    """
    res = {}
    for mod_id, mod_info in modules.items():
        mod_info = dict(mod_info)
        mod_type = dict(module_types[mod_info["type"]])
        # Directly copy any fields only defined on the type
        if "repository" in mod_type:
            mod_info["repository"] = mod_type["repository"]
        mod_info["header_file"] = mod_type["header_file"]
        mod_info["class_name"] = mod_type["class_name"]
        if "dependencies" in mod_type:
            mod_info["dependencies"] = mod_type["dependencies"]
        # Update the arguments
        args = list(mod_info.get("arguments", []))
        type_args = list(mod_type.get("arguments", []))
        if len(args) > len(type_args):
            raise RuntimeError(
                'Too many arguments specified for module "{}". (Got {}, '
                'expected {})'.format(
                    mod_id, len(args), len(type_args)
                )
            )
        for i in range(len(args), len(type_args)):
            arg_info = type_args[i]
            if "default" in arg_info:
                args.append(arg_info["default"])
            else:
                raise RuntimeError(
                    'Not enough module arguments supplied for module "{}" '
                    '(Got {}, expecting {})'.format(
                        mod_id, len(args), len(type_args)
                    )
                )
        mod_info["arguments"] = args
        # Update the inputs
        mod_inputs = mod_info.get("inputs", {})
        for input_name, type_input_info in mod_type.get("inputs", {}).items():
            mod_input_info = dict(type_input_info)
            mod_input_info.update(mod_inputs.get(input_name, {}))
            mod_input_info["variable"] = mod_input_info.get(
                "variable", input_name
            )
            mod_input_info["categories"] = mod_input_info.get(
                "categories", [ACTUATORS]
            )
            mod_inputs[input_name] = mod_input_info
        mod_info["inputs"] = mod_inputs
        # Update the outputs
        mod_outputs = mod_info.get("outputs", {})
        for output_name, type_output_info in mod_type.get("outputs", {}).items():
            mod_output_info = dict(type_output_info)
            mod_output_info.update(mod_outputs.get(output_name, {}))
            mod_output_info["variable"] = mod_output_info.get(
                "variable", output_name
            )
            mod_output_info["categories"] = mod_output_info.get(
                "categories", [SENSORS]
            )
            mod_outputs[output_name] = mod_output_info
        mod_info["outputs"] = mod_outputs
        res[mod_id] = mod_info
    return res

def index_by_id(docs):
    """Index a list of docs using `_id` field.
    Returns a dictionary keyed by _id."""
    return {doc["_id"]: doc for doc in docs}

def dedupe_by(things, key=None):
    """
    Given an iterator of things and an optional key generation function, return
    a new iterator of deduped things. Things are compared and de-duped by the
    key function, which is hash() by default.
    """
    if not key:
        key = hash
    index = {key(thing): thing for thing in things}
    return index.values()

def make_dir_name_from_url(url):
    """This function attempts to emulate something like Git's "humanish"
    directory naming for clone. It's probably not a perfect facimile,
    but it's close."""
    url_path = urlparse(url).path
    head, tail = os.path.split(url_path)
    # If tail happens to be empty as in case `/foo/`, use foo.
    # If we are looking at a valid but ugly path such as
    # `/foo/.git`, use the "foo" not the ".git".
    if len(tail) is 0 or tail[0] is ".":
        head, tail = os.path.split(head)
    dir_name, ext = os.path.splitext(tail)
    return dir_name

def load_firmware_module_type_file(module_file_path):
    f = open(module_file_path)
    doc = json.load(f)
    if not doc.get("_id"):
        # Derive id from dirname if id isn't present
        dir_name = os.path.basename(os.path.dirname(module_file_path))
        doc["_id"] = dir_name
    return FirmwareModuleType(doc)

def load_firmware_types_from_lib(lib_path):
    """
    Given a lib_path, generates a list of firmware module types by looking for
    module.json files in a lib directory.
    """
    for dir_name in os.listdir(lib_path):
        dir_path = os.path.join(lib_path, dir_name)
        if not os.path.isdir(dir_path):
            continue
        config_path = os.path.join(dir_path, "module.json")
        if os.path.isfile(config_path):
            click.echo(
                "Parsing firmware module type \"{}\" from lib "
                "folder".format(dir_name)
            )
            yield load_firmware_module_type_file(config_path)

def load_firmware_types_from_db(server):
    """Given a Couch database server instance, generate firmware type docs."""
    db = server[FIRMWARE_MODULE_TYPE]
    for _id in db:
        # Skip design documents
        if _id.startswith("_"):
            continue
        click.echo("Parsing firmware module type \"{}\" from DB".format(_id))
        doc = db[_id]
        firmware_type = FirmwareModuleType(doc)
        yield firmware_type

def load_firmware_from_db(server):
    """Given a reference to a server instance, generate modules."""
    db = server[FIRMWARE_MODULE]
    for _id in db:
        if _id.startswith("_"):
            continue
        click.echo("Parsing firmware module \"{}\"".format(_id))
        module = FirmwareModule(db[_id])
        yield module
