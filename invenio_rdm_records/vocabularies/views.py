# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 CERN.
# Copyright (C) 2019 Northwestern University.
#
# Invenio-RDM-Records is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.


"""Invenio vocabularies views."""


def create_affiliations_blueprint_from_app(app):
    """Create app blueprint."""
    return app.extensions["invenio-rdm-records"].affiliations_resource \
        .as_blueprint()


def create_subjects_blueprint_from_app(app):
    """Create app blueprint."""
    return app.extensions["invenio-rdm-records"].subjects_resource \
        .as_blueprint()
