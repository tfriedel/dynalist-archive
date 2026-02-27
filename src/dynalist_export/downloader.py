"""Download and process Dynalist documents."""

import copy
import io
import logging
import re
from typing import Any

from dynalist_export.protocols import ApiProtocol, WriterProtocol


class Downloader:
    """Download raw data, give each record a name, and save them to a directory.

    Assigns names to each record, too.
    """

    def __init__(self, writer: WriterProtocol) -> None:
        self._writer = writer
        self.logger = logging.getLogger("downloader")

        # Output: file index, including folder. List of api(file/list) objects,
        # augmented with 'version' and '_path' fields
        self.file_index: list[dict[str, Any]] | None = None

        # Output: document contents. Map filename -> api(doc/read) objects.
        self.doc_contents: dict[str, dict[str, Any]] | None = None

    def sync_all(self, api: ApiProtocol) -> None:
        """Sync all raw data to the local directory."""
        raw_file_list = self._sync_file_list(api)
        versions_info = self._get_versions_info(api, raw_file_list)
        self.file_index = self._assign_obj_filenames(raw_file_list)

        self.doc_contents = self._get_contents(api, self.file_index, versions_info)

        self._make_processed_files(self.doc_contents)

    def _sync_file_list(self, api: ApiProtocol) -> dict[str, Any]:
        """Update file list, generate name for each file.

        Returns:
            Augmented list of files (like file/list API, but with extra version fields).
        """
        files = api.call("file/list", {})
        # Guard against API changes
        if files.keys() != {"root_file_id", "files", "_code"}:
            msg = f"bad files keys: {files.keys()!r}"
            raise ValueError(msg)

        # Record raw list. Leading underscore guarantees no collisions.
        self._writer.make_data_file("_raw_list.json", data=files)
        return files

    def _get_versions_info(self, api: ApiProtocol, files: dict[str, Any]) -> dict[str, int]:
        # Augment data with version numbers -- we fetch version for each document right away.
        all_file_ids = sorted(x["id"] for x in files["files"] if x["type"] != "folder")
        versions = api.call("doc/check_for_updates", {"file_ids": all_file_ids})
        if versions.keys() != {"versions", "_code"}:
            msg = f"bad versions keys: {versions.keys()!r}"
            raise ValueError(msg)

        self._writer.make_data_file("_raw_versions.json", data=versions)
        versions_set = set(versions["versions"])
        file_id_set = {x["id"] for x in files["files"] if x["type"] != "folder"}

        self.logger.debug(
            f"Versions call: got {len(versions_set.intersection(file_id_set))} matches, "
            f"{len(file_id_set.difference(versions_set))} files without versions, "
            f"{len(versions_set.difference(file_id_set))} versions without files"
        )

        return versions["versions"]  # type: ignore[no-any-return]

    def _assign_obj_filenames(self, raw_list: dict[str, Any]) -> list[dict[str, Any]]:
        """Walk hierarchy, assign a filename to each file."""
        # (could have done it recursively, but I don't like too many parameters)
        to_process = {f["id"]: f for f in raw_list["files"]}
        todo: list[tuple[str, str]] = [("", raw_list["root_file_id"])]

        # We produce a list of files in pre-order (same order as shown in UI)
        file_list: list[dict[str, Any]] = []

        while todo:
            path_prefix, file_id = todo.pop(0)
            file_obj = to_process.pop(file_id)

            # Generate the unique name for this object. Note we strip leading/trailing
            # underscores and dots to prevent surprises, or dirnames overlapping filenames.
            base_name = path_prefix + (
                re.sub(r"([^A-Za-z0-9()_. -]+)", "_", file_obj["title"]).strip("_. -") or "unnamed"
            )
            if file_id == raw_list["root_file_id"]:
                base_name = "_root_file"

            # Write the raw file right away
            fname = self._writer.make_unique_name(base_name)
            obj_type = file_obj["type"]
            if obj_type not in ("folder", "document"):
                msg = f"unexpected object type: {obj_type!r}"
                raise ValueError(msg)

            next_prefix = fname + "/"
            file_obj_new = dict(file_obj)
            # Force first-level folders to be toplevel
            if file_id == raw_list["root_file_id"]:
                if obj_type != "folder":
                    msg = "root file is not a folder"
                    raise ValueError(msg)
                next_prefix = ""
                file_obj_new["_is_root"] = True

            todo = [(next_prefix, cid) for cid in file_obj.get("children", [])] + todo

            file_obj_new["_path"] = fname
            file_list.append(file_obj_new)

        if to_process:
            msg = f"Orphan file entries found: {sorted(to_process.keys())!r}"
            raise ValueError(msg)

        # To avoid too much churn, only store name/id pairs.
        self._writer.make_data_file(
            "_raw_filenames.json",
            data=[{"_path": x["_path"], "id": x["id"]} for x in file_list],
        )

        return file_list

    def _get_contents(
        self,
        api: ApiProtocol,
        file_index: list[dict[str, Any]],
        versions_info: dict[str, int],
    ) -> dict[str, dict[str, Any]]:
        doc_contents: dict[str, dict[str, Any]] = {}
        num_changed = 0

        for file_obj in file_index:
            if file_obj["type"] != "document":
                continue
            path = file_obj["_path"]
            obj_id = file_obj["id"]
            expected_version = versions_info.get(obj_id)

            last_contents = self._writer.try_read_json(path + ".c.json")

            if (
                last_contents is not None
                and expected_version is not None
                and last_contents["version"] == expected_version
            ):
                contents = last_contents
            else:
                stored_version = last_contents["version"] if last_contents else "(not stored)"
                self.logger.debug(
                    f"Fetching document {path!r} (id {obj_id!r}), "
                    f"version: expected {expected_version!r}, stored {stored_version!r}"
                )
                contents = api.call("doc/read", {"file_id": obj_id})
                code = contents.pop("_code")
                if code != "Ok":
                    msg = f"bad code: {code!r} ({contents.get('_msg')!r})"
                    raise RuntimeError(msg)
                num_changed += 1

            # Either way, write the file back, else it will be deleted from disk.
            self._writer.make_data_file(path + ".c.json", data=contents)
            doc_contents[path] = contents

        if num_changed:
            self.logger.info(f"Found {len(doc_contents)} documents, {num_changed} changed")
        else:
            self.logger.debug(f"Found {len(doc_contents)} documents, none changed")
        return doc_contents

    def _make_processed_files(self, doc_contents: dict[str, dict[str, Any]]) -> None:
        for path, contents in sorted(doc_contents.items()):
            as_text = _record_to_text(contents)
            self._writer.make_data_file(path + ".txt", contents=as_text)


def _iterate_contents(contents: dict[str, Any]) -> Any:
    """Walk all items in in-order given a contents value (from doc/read API).

    Yields:
        All nodes, freshly deepcopied, with extra field:
        _parents -- list of node parent id's.
        The return values can be safely modified at will.
    """
    to_return = {x["id"]: copy.deepcopy(x) for x in contents["nodes"]}
    # It is not documented, but looks like top-level node always has an id of 'root'.
    # Let's assume this is the case (and we'd fail if this is not true)

    todo: list[tuple[str, list[str]]] = [("root", [])]
    while todo:
        node_id, parents = todo.pop(0)
        data = copy.deepcopy(to_return.pop(node_id))
        data.update(_parents=parents)
        todo = [(child, [*parents, node_id]) for child in data.get("children", ())] + todo
        yield data

    if to_return:
        msg = f"found orphaned nodes: {sorted(to_return.keys())!r}"
        raise ValueError(msg)


def _dict_to_readable(val_dict: dict[str, Any]) -> str:
    parts: list[str] = []
    for k, v in sorted(val_dict.items()):
        if v is True:
            parts.append(k)
            continue

        if repr(v) == f'"{v}"' and "," not in str(v):
            v_str = str(v)  # Safe string representation
        else:
            v_str = repr(v)  # Unsafe string representation
        parts.append(f"{k}={v_str}")
    return ", ".join(parts)


def _record_to_text(contents: dict[str, Any]) -> str:
    """Convert a single record to text.

    The text is optimized for git diffs.

    Note that the conversion is intentionally somewhat lossy -- things which
    are not part of content (like collapse status or version numbers) are not included.
    """
    out = io.StringIO()

    meta = copy.copy(contents)
    meta.pop("nodes")
    meta.pop("file_id")
    meta.pop("version")
    print(f"### FILE: {meta.pop('title')}", file=out)
    if meta:
        print("# meta: " + _dict_to_readable(meta), file=out)

    for node in _iterate_contents(contents):
        spacer = " " * (4 * len(node.pop("_parents")))
        node.pop("children", None)  # Do not care
        node.pop("id")
        node.pop("collapsed", None)  # Logically, "collapsed" is not part of content
        note = node.pop("note")
        _ctime, _mtime = node.pop("created"), node.pop("modified")

        # Print content. First line gets '*', the rest get '.'
        for lnum, line in enumerate(node.pop("content").split("\n")):
            print(spacer + (". " if lnum else "* ") + line, file=out)

        # Print notes, if we have them.
        if note:
            for line in note.splitlines():
                print(spacer + "_ " + line, file=out)

        # Finally, the rest
        if node:
            print(spacer + "# " + _dict_to_readable(node), file=out)

    return out.getvalue()
