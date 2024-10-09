# -*- coding: utf-8 -*-
#
# Copyright (C) 2024 CERN.
#
# Invenio-RDM is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.
"""Collections programmatic API."""
from luqum.parser import parser as luqum_parser
from werkzeug.utils import cached_property

from .errors import CollectionNotFound, CollectionTreeNotFound, InvalidQuery
from .models import Collection as CollectionModel
from .models import CollectionTree as CollectionTreeModel


class ModelField:
    """Model Field Descriptor."""

    def __init__(self, attr_name):
        """Initialize the descriptor."""
        self._attr_name = attr_name

    @property
    def attr_name(self):
        """The name of the SQLAlchemy field on the model.

        Defaults to the attribute name used on the class.
        """
        return self._attr_name

    def __get__(self, obj, objtype=None):
        """Descriptor method to get the object."""
        if obj is None:
            return self

        # Try instance access
        try:
            return getattr(obj.model, self.attr_name)
        except AttributeError:
            return None


class Collection:
    """Collection Object."""

    model_cls = CollectionModel

    id = ModelField("id")
    path = ModelField("path")
    ctree_id = ModelField("collection_tree_id")
    order = ModelField("order")
    title = ModelField("title")
    slug = ModelField("slug")
    depth = ModelField("depth")
    search_query = ModelField("search_query")
    num_records = ModelField("num_records")

    def __init__(self, model=None, max_depth=2):
        """Instantiate a Collection object."""
        self.model = model
        self.max_depth = max_depth

    @classmethod
    def validate_query(cls, query):
        """Validate the collection query."""
        try:
            luqum_parser.parse(query)
        except Exception:
            raise InvalidQuery()

    @classmethod
    def create(cls, slug, title, query, ctree=None, parent=None, order=None, depth=2):
        """Create a new collection."""
        _ctree = None
        if parent:
            path = f"{parent.path}{parent.id},"
            _ctree = parent.collection_tree.model
        elif ctree:
            path = ","
            _ctree = ctree if isinstance(ctree, int) else ctree.model
        else:
            raise ValueError("Either parent or ctree must be set.")

        Collection.validate_query(query)
        return cls(
            cls.model_cls.create(
                slug=slug,
                path=path,
                title=title,
                search_query=query,
                order=order,
                ctree_or_id=_ctree,
            ),
            depth,
        )

    @classmethod
    def resolve(cls, id_=None, slug=None, ctree_id=None, depth=2):
        """Resolve a collection by ID or slug.

        To resolve by slug, the collection tree ID must be provided.
        """
        res = None
        if id_:
            res = cls(cls.model_cls.get(id_), depth)
        elif slug and ctree_id:
            res = cls(cls.model_cls.get_by_slug(slug, ctree_id), depth)
        else:
            raise ValueError(
                "Either ID or slug and collection tree ID must be provided."
            )

        if res.model is None:
            raise CollectionNotFound()
        return res

    @classmethod
    def resolve_many(cls, ids_=None, depth=2):
        """Resolve many collections by ID."""
        _ids = ids_ or []
        return [cls(c, depth) for c in cls.model_cls.read_many(_ids)]

    def add(self, slug, title, query, order=None, depth=2):
        """Add a subcollection to the collection."""
        return self.create(
            slug=slug, title=title, query=query, parent=self, order=order, depth=depth
        )

    @property
    def collection_tree(self):
        """Get the collection tree object.

        Note: this will execute a query to the collection tree table.
        """
        return CollectionTree(self.model.collection_tree)

    @cached_property
    def community(self):
        """Get the community object."""
        return self.collection_tree.community

    @property
    def query(self):
        """Get the collection query."""
        q = ""
        for _a in self.ancestors:
            q += f"({_a.model.search_query}) AND "
        q += f"({self.model.search_query})"
        Collection.validate_query(q)
        return q

    @cached_property
    def ancestors(self):
        """Get the collection ancestors."""
        return Collection.resolve_many(self.split_path_to_ids())

    @cached_property
    def sub_collections(self):
        """Fetch descendants.

        If the max_depth is 1, fetch only direct descendants.
        """
        if self.max_depth == 0:
            return []

        if self.max_depth == 1:
            return self.get_children()

        return self.get_subcollections()

    @cached_property
    def children(self):
        """Fetch only direct descendants."""
        return self.get_children()

    def split_path_to_ids(self):
        """Return the path as a list of integers."""
        if not self.model:
            return None
        return [int(part) for part in self.path.split(",") if part.strip()]

    def get_children(self):
        """Get the collection first level (direct) children.

        More preformant query to retrieve descendants, executes an exact match query.
        """
        if not self.model:
            return None
        res = self.model_cls.get_children(self.model)
        return [type(self)(r) for r in res]

    def get_subcollections(self):
        """Get the collection subcollections.

        This query executes a LIKE query on the path column.
        """
        if not self.model:
            return None

        res = self.model_cls.get_subcollections(self.model, self.max_depth)
        return [type(self)(r) for r in res]

    def __repr__(self) -> str:
        """Return a string representation of the collection."""
        if self.model:
            return f"Collection {self.id} ({self.path})"
        else:
            return "Collection (None)"

    def __eq__(self, value: object) -> bool:
        """Check if the value is equal to the collection."""
        return isinstance(value, Collection) and value.id == self.id


class CollectionTree:
    """Collection Tree Object."""

    model_cls = CollectionTreeModel

    id = ModelField("id")
    title = ModelField("title")
    slug = ModelField("slug")
    community_id = ModelField("community_id")
    order = ModelField("order")
    community = ModelField("community")
    collections = ModelField("collections")

    def __init__(self, model=None, max_depth=2):
        """Instantiate a CollectionTree object."""
        self.model = model
        self.max_depth = max_depth

    @classmethod
    def create(cls, title, slug, community_id=None, order=None):
        """Create a new collection tree."""
        return cls(
            cls.model_cls.create(
                title=title, slug=slug, community_id=community_id, order=order
            )
        )

    @classmethod
    def resolve(cls, id_=None, slug=None, community_id=None):
        """Resolve a CollectionTree."""
        res = None
        if id_:
            res = cls(cls.model_cls.get(id_))
        elif slug and community_id:
            res = cls(cls.model_cls.get_by_slug(slug, community_id))
        else:
            raise ValueError("Either ID or slug and community ID must be provided.")

        if res.model is None:
            raise CollectionTreeNotFound()
        return res

    @cached_property
    def collections(self):
        """Get the collections under this tree."""
        root_collections = CollectionTreeModel.get_collections(self.model, 1)
        return [Collection(c, self.max_depth) for c in root_collections]

    @classmethod
    def get_community_trees(cls, community_id, depth=2):
        """Get all the collection trees for a community."""
        return [cls(c, depth) for c in cls.model_cls.get_community_trees(community_id)]
