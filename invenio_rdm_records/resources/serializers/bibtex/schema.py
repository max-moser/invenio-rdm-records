# -*- coding: utf-8 -*-
#
# Copyright (C) 2023-2025 CERN
#
# Invenio-RDM-Records is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""BibTex based Schema for Invenio RDM Records."""

import calendar
import textwrap

from babel_edtf import parse_edtf
from edtf.parser.grammar import ParseException
from edtf.parser.parser_classes import Date, Interval
from flask_resources.serializers import BaseSerializerSchema
from marshmallow import fields, missing, post_dump
from pydash import py_
from slugify import slugify

from ..schemas import CommonFieldsMixin
from .schema_formats import BibTexFormatter


class BibTexSchema(BaseSerializerSchema, CommonFieldsMixin):
    """Schema for records in BibTex."""

    id = fields.Method("get_id")
    resource_id = fields.Str(attribute="metadata.resource_type.id")
    version = fields.Str(attribute="metadata.version")
    date_published = fields.Method("get_date_published")
    locations = fields.Method("get_locations")
    titles = fields.Method("get_titles")
    doi = fields.Method("get_doi")
    creators = fields.Method("get_creators")
    creator = fields.Method("get_creator")
    publishers = fields.Method("get_publishers")
    contributors = fields.Method("get_contributors")
    school = fields.Method("get_school")
    journal = fields.Method("get_journal")
    volume = fields.Method("get_volume")
    booktitle = fields.Method("get_booktitle")
    number = fields.Method("get_number")
    pages = fields.Method("get_pages")
    note = fields.Method("get_note")
    venue = fields.Method("get_venue")
    url = fields.Method("get_url")

    entry_mapper = {
        # Publication fields
        "publication-conferencepaper": [BibTexFormatter.in_proceedings],
        "publication-conferenceproceeding": [BibTexFormatter.proceedings],
        "publication-book": [
            BibTexFormatter.book,
            BibTexFormatter.booklet,
        ],
        "publication-section": [
            BibTexFormatter.in_collection,
            BibTexFormatter.in_book,
        ],
        "publication-article": [BibTexFormatter.article],
        "publication-preprint": [BibTexFormatter.unpublished],
        "publication-thesis": [BibTexFormatter.thesis],
        "publication-technicalnote": [BibTexFormatter.manual],
        "publication-workingpaper": [BibTexFormatter.unpublished],
        # Software
        "software": [BibTexFormatter.software],
        "dataset": [BibTexFormatter.dataset],
    }
    """Maps resource types to formats."""

    @property
    def default_entry_type(self):
        """Read-only property that defines the default bibtex entry type to be used.

        The default type can be used when a resource type is not explicitely defined in ``format_mapper``.
        """
        return BibTexFormatter.misc

    def get_id(self, obj):
        """Get record id."""
        if self.context.get("doi_all_versions", False):
            # If all versions export is requested, return the parent id
            return obj["parent"]["id"]
        return obj["id"]

    def get_date_published(self, obj):
        """Get publication year and month from edtf date."""
        publication_date = py_.get(obj, "metadata.publication_date")
        if not publication_date:
            return None

        try:
            parsed_date = parse_edtf(publication_date)
        except ParseException:
            return None

        if isinstance(parsed_date, Interval):
            # if date is an interval, use the start date
            parsed_date = parsed_date.lower
        elif not isinstance(parsed_date, Date):
            return None

        date_published = {"year": parsed_date.year}
        if parsed_date.month:
            month_three_letter_abbr = calendar.month_abbr[
                int(parsed_date.month)
            ].lower()
            date_published["month"] = month_three_letter_abbr

        return date_published

    def get_creator(self, obj):
        """Get creator."""
        creator = obj["metadata"]["creators"][0]["person_or_org"]
        return {
            "name": creator["name"],
        }

    def get_booktitle(self, obj):
        """Retrieves ``booktitle`` from record's custom fields.

        :returns: book title, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("imprint:imprint", {}).get("title")

    def get_pages(self, obj):
        """Retrieves ``bookpages`` from record's custom fields.

        :returns: book pages, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("imprint:imprint", {}).get("pages")

    def get_venue(self, obj):
        """Retrieves ``venue`` from record's meeting custom fields.

        :returns: conference venue, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("meeting:meeting", {}).get("place")

    def get_note(self, obj):
        """Retrieves ``note`` from record's additional descriptions.

        The final note is generated by stacking all the additional descriptions of type ``other``.s

        :returns: additional note, if found, ``None``otherwise.
        """
        note = ""
        for description in obj.get("additional_descriptions", []):
            if description["type"]["id"] == "other":
                description_text = description["description"]
                note += f"{description_text}\n"
        return note if len(note) else None

    def get_number(self, obj):
        """Retrieves ``number`` from record's custom fields.

        :returns: journal issue, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("journal:journal", {}).get("issue")

    def get_volume(self, obj):
        """Retrieves ``volume`` from record's custom fields.

        :returns: journal volume, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("journal:journal", {}).get("volume")

    def get_journal(self, obj):
        """Retrieves ``journal`` from record's custom fields.

        :returns: journal title, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("journal:journal", {}).get("title")

    def get_school(self, obj):
        """Retrieves ``school`` from record's custom fields.

        :returns: thesis university, if found, ``None``otherwise.
        """
        return obj.get("custom_fields", {}).get("thesis:university")

    def get_url(self, obj):
        """Generate url."""
        doi = self.get_doi(obj)
        url = None
        if doi is not missing:
            url = f"https://doi.org/{doi}"
        return url

    @post_dump(pass_original=True)
    def dump_record(self, data, original, many, **kwargs):
        """Dumps record."""
        resource_type = data["resource_id"]

        fields_map = self._fetch_fields_map(data)

        entry = self._get_bibtex_entry(resource_type, fields_map)

        entry_fields = entry["req_fields"] + entry["opt_fields"]

        dumped_record = self._dump_data(
            entry["name"], entry_fields, fields_map, data, original
        )
        return dumped_record

    def _get_bibtex_entry(self, resource_type, fields_map):
        """Retrieves the Bibtex entry type for a record's resource type.

        Defaults to ``self.default_format``.

        .. code-block:: python

            format = {
                "name": "misc",
                "req_fields": [],
                "opt_fields": ["author", "title", "month", "year", "note", "publisher", "version"]
            }


        :returns: an object with the bibtex fields for the resource types.
        """
        # Every resource type is mapped to a default
        entry = self.default_entry_type
        if entries := self.entry_mapper.get(resource_type):
            for _entry in entries:
                success = all([fields_map.get(f) for f in _entry["req_fields"]])
                if success:
                    entry = _entry
                    break
        return entry

    def _dump_data(self, name, entry_fields, fields, data, original):
        """Dumps record data into the Bibtex format.

        :returns: the Bibtex string formatted.
        """
        out = "@" + name + "{"
        out += self._get_citation_key(data, original) + ",\n"
        fields_string = self._parse_fields(entry_fields, fields)
        out += self._clean_input(fields_string)
        out += "}"
        return out

    def _parse_fields(self, entry_fields, fields):
        """Parses fields into a single string."""
        out = ""
        for field in entry_fields:
            value = fields.get(field)
            if value is not None:
                out += self._format_output_row(field, value)
        return out

    def _fetch_fields_map(self, data):
        """Retrieves fields from the record."""
        # The following fields are taken from Zenodo for consistency/compatibility reasons
        return {
            "address": data.get("locations", None),
            "author": data.get("creators", None),
            "publisher": (
                lambda publishers: None if publishers is None else publishers[0]
            )(data.get("publishers", None)),
            "title": (lambda titles: None if titles is None else titles[0])(
                data.get("titles", None)
            ),
            "year": data.get("date_published", {}).get("year", None),
            "doi": data.get("doi", None),
            "month": data.get("date_published", {}).get("month", None),
            "version": data.get("version", None),
            "url": data.get("url", None),
            "school": data.get("school", None),
            "journal": data.get("journal", None),
            "volume": data.get("volume", None),
            "booktitle": data.get("booktitle", None),
            "number": data.get("number", None),
            "pages": data.get("pages", None),
            "note": data.get("note", None),
            "venue": data.get("venue", None),
            "swhid": data.get("swhid", None),
        }

    def _format_output_row(self, field, value):
        out = ""
        if isinstance(value, str):
            value = value.strip()
        if field == "author":
            out += "  {0:<12} = ".format(field) + "{"
            out += value[0] + (" and\n" if len(value) > 1 else "")
            out += " and\n".join(
                [" {0:<16} {1:<}".format("", line) for line in value[1::]]
            )
            out += "},\n"

        elif len(value) > 50:
            wrapped = textwrap.wrap(value, 50)
            out = f"  {field:<12} = {{{wrapped[0]}\n"
            for line in wrapped[1:]:
                out += f" {'' :<17} {line}\n"
            out += f" {'' :<17}}},\n"  # Closing the single brace here
        elif field == "month":
            out = "  {0:<12} = {1},\n".format(field, value)
        elif field == "url":
            out = "  {0:<12} = {{{1}}},\n".format(field, value)
        else:
            if not isinstance(value, list) and value.isdigit():
                out = "  {0:<12} = {1},\n".format(field, value)
            else:
                out = "  {0:<12} = {{{1}}},\n".format(field, value)
        return out

    def _get_citation_key(self, data, original_data):
        """Return citation key."""
        id = data["id"]

        creators = original_data["metadata"].get("creators", [])
        if not creators:
            return id

        creator = creators[0].get("person_or_org", {})
        name = creator.get("family_name", creator["name"])
        pubdate = data.get("date_published", {}).get("year", None)
        year = id
        if pubdate is not None:
            year = "{}_{}".format(pubdate, id)
        return "{0}_{1}".format(slugify(name, separator="_", max_length=40), year)

    def _clean_input(self, input):
        unsupported_chars = ["&", "%", "$", "_", "#"]
        chars = list(input)
        for index, char in enumerate(chars):
            if char in unsupported_chars:
                chars[index] = "\\" + chars[index]
        return "".join(chars)
