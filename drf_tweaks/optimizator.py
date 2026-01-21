import logging

from distutils.version import LooseVersion
from django import get_version
from drf_tweaks.serializers import filter_fields
from rest_framework.serializers import ListSerializer, Serializer

from django.db.models.fields import related_descriptors

from rest_framework.serializers import (
    BaseSerializer,
    ListSerializer,
    ManyRelatedField,
    PrimaryKeyRelatedField,
    RelatedField,
    Serializer,
    SerializerMethodField,
)

from .serializers import filter_fields
from .fields import AsymetricRelatedField

_logger = logging.getLogger(__name__)


class BaseOptimizer:
    related_field_class = (
        RelatedField,
        BaseSerializer,
        ManyRelatedField,
        SerializerMethodField,
    )

    def __init__(self, only_fields: set, include_fields: set):
        self.only_fields = only_fields
        self.include_fields = include_fields

    @staticmethod
    def check_if_related_object(model_field: object):
        """
        Check if object is on One to One or Reverse ForeignKey relationship

        :param model_field: django field
        """
        return any(
            isinstance(model_field, x)
            for x in (
                related_descriptors.ForwardManyToOneDescriptor,
                related_descriptors.ReverseOneToOneDescriptor,
            )
        )

    @staticmethod
    def check_if_prefetch_object(model_field: object):
        """
        Check if objects is on Many To One or ForeignKey relationship.

        :param model_field: django field
        """
        return any(
            isinstance(model_field, x)
            for x in (
                related_descriptors.ManyToManyDescriptor,
                related_descriptors.ReverseManyToOneDescriptor,
            )
        )

    @staticmethod
    def filter_field_name(field_name: str, fields_to_serialize: list):
        """
        Check if field need to be serialized.

        :param field_name: field name
        :param fields_to_serialize: list of fields to serialize
        """
        if fields_to_serialize is not None:
            return filter_fields(field_name, fields_to_serialize)
        return None

    @staticmethod
    def clean_fields(prefetch_set: set, select_set: set):
        """In case if the discovery set ManytoOne in select related."""
        return select_set - prefetch_set

    def check_in_fields(self, model_class, model_field):
        """
        Check if field is not a property.
        Check if field in model class related or in reverse related fields.

        :param model_class: Django model class
        :param model_field: Django model field
        :return: True if field is not a property and if the relation is established.
        """
        if isinstance(model_field, property):
            return False

        rel = None
        if isinstance(model_field, related_descriptors.ReverseOneToOneDescriptor):
            rel = model_field.related

        elif any(
            isinstance(model_field, x)
            for x in (
                related_descriptors.ManyToManyDescriptor,
                related_descriptors.ForwardManyToOneDescriptor,
            )
        ):
            rel = model_field.field

        elif isinstance(model_field, related_descriptors.ReverseManyToOneDescriptor):
            rel = model_field.rel

        return rel in model_class._meta.get_fields()

    def check_if_needs_serialization(
        self, serializer: object, field_name: str, on_demand_fields: set
    ):
        """
        Use serializer method to check if field need to be serialized or not.

        :param serializer: serializer object
        :param field_name: field name
        :param on_demand_fields: list of request on demand fields
        """
        if hasattr(serializer, "check_if_needs_serialization"):
            return serializer.check_if_needs_serialization(
                field_name, self.only_fields, self.include_fields, on_demand_fields
            )
        return False

    def get_optimizer(self, field: object, field_name: str):
        """
        Get sub optimizer class according to type of field.

        :param field: field object
        :param field_name: field name
        :return: Sub Optimizer class
        """
        child_only_fields = self.filter_field_name(field_name, self.only_fields)
        child_include_fields = self.filter_field_name(field_name, self.include_fields)
        field_type = type(field)

        # Simple field relation
        if "." in field.source:
            return SourceSerializerAutoOptimizer(
                child_only_fields, child_include_fields
            )

        if field_type == SerializerMethodField:
            return SerializerMethodFieldAutoOptimizer(
                child_only_fields, child_include_fields
            )
        if field_type == PrimaryKeyRelatedField:
            return PrimaryKeyRelatedFieldAutoOptimizer(
                child_only_fields, child_include_fields
            )
        if field_type == RelatedField:
            return SimpleRelationAutoOptimizer(child_only_fields, child_include_fields)
        if field_type == AsymetricRelatedField:
            return AsymetricRelatedFieldAutoOptimizer(
                child_only_fields, child_include_fields
            )

        # Nested Serializers
        if isinstance(field, ListSerializer):
            return ListSerializerAutoOptimizer(child_only_fields, child_include_fields)
        if isinstance(field, Serializer):
            return SimpleSerializerAutoOptimizer(
                child_only_fields, child_include_fields
            )
        if isinstance(field, ManyRelatedField):
            return ManyRelatedFieldAutoOptimizer(
                child_only_fields, child_include_fields
            )
        return None

    def optimize(self, *args, **kwargs):
        raise NotImplementedError

    def get_field_to_handle(self, serializer: object, on_demand_fields: set):
        """
        Generate list of related fields

        :param serializer: serializer or field object
        :param on_demand_fields: set of fields requested by api call
        :yield: field name, field object
        """
        for field_name, field in serializer.fields.items():
            if not self.check_if_needs_serialization(
                serializer, field_name, on_demand_fields
            ):
                continue

            if not (
                isinstance(field, self.related_field_class) or ("." in field.source)
            ):
                continue

            if isinstance(field, AsymetricRelatedField) and (
                field_name not in self.include_fields
            ):
                continue

            yield field_name, field


class ManyRelationAutoOptimizer(BaseOptimizer):
    def optimize(
        self,
        field: object,
        prefix: str,
        model_class: object,
        to_prefetch: bool,
        *args,
        **kwargs,
    ):
        """
        Common method to handle select related or prefetch related field

        :param field: field to check.
        :param prefix: path to add field on related fields
        :param to_prefetch: if need to add field in prefetch related field list
        :return: set contains select and prefetch related fields
        """
        prefetch_related_set = set()
        select_related_set = set()
        model_field = getattr(model_class, field.source, None)

        serializer = self.get_serializer(field)
        if serializer is None or model_field is None:
            return select_related_set, prefetch_related_set

        # No attribut meta (ex. serializer.Serializer to manage a dict/json field)
        if not hasattr(serializer, "Meta"):
            return select_related_set, prefetch_related_set

        if not hasattr(serializer.Meta, "model"):
            return select_related_set, prefetch_related_set

        if not self.check_in_fields(model_class, model_field):
            return select_related_set, prefetch_related_set

        if self.check_if_related_object(model_field) and not to_prefetch:
            select_related_set.add(prefix + field.source)
        else:
            prefetch_related_set.add(prefix + field.source)
            to_prefetch = True

        prefix += f"{field.source}__"

        model_class = serializer.Meta.model
        on_demand_fields = getattr(serializer, "get_on_demand_fields", set)()

        fields_to_optimize = (
            (field_name, field)
            for field_name, field in self.get_field_to_handle(
                serializer, on_demand_fields
            )
            if getattr(model_class, field_name, False)
            and self.check_if_needs_serialization(
                serializer, field_name, on_demand_fields
            )
        )

        for field_name, field in fields_to_optimize:
            optimizer = self.get_optimizer(field, field_name)
            if optimizer is None:
                continue

            select_fields, prefetch_fields = optimizer.optimize(
                field=field,
                prefix=prefix,
                model_class=model_class,
                to_prefetch=to_prefetch,
            )
            prefetch_related_set |= prefetch_fields
            select_related_set |= select_fields

        return select_related_set, prefetch_related_set


# ------------------- not iterable -------------------


class SimpleRelationAutoOptimizer(BaseOptimizer):
    def optimize(
        self, field: object, prefix: str, model_class: object, to_prefetch: bool
    ):
        """
        Method to optimize simple field (field to be sure to have no recurtion).

        :param field: field object
        :param prefix: path to add field on related fields
        :param model_class: model class
        :param to_prefetch: if need to add field in prefetch related field list
        :return: sets contains select and prefetch related fields
        """
        prefetch_related_set = set()
        select_related_set = set()

        # Use get field name to know which field to add if field set
        field_name = self.get_field_name(field)

        if hasattr(model_class, field_name):
            model_field = getattr(model_class, field_name)
            if self.check_if_related_object(model_field):
                if to_prefetch:
                    prefetch_related_set.add(prefix + field_name)
                else:
                    select_related_set.add(prefix + field_name)

        return select_related_set, prefetch_related_set


class SourceSerializerAutoOptimizer(SimpleRelationAutoOptimizer):
    def get_field_name(self, field: object):
        return field.source.split(".", 1)[0]


class SerializerMethodFieldAutoOptimizer(SimpleRelationAutoOptimizer):
    def get_field_name(self, field: object):
        return field.field_name


class PrimaryKeyRelatedFieldAutoOptimizer(SimpleRelationAutoOptimizer):
    def get_field_name(self, field: object):
        return field.field_name


# ------------------- iterable -------------------


class ListSerializerAutoOptimizer(ManyRelationAutoOptimizer):
    def get_serializer(self, field: object):
        """
        Method to check and handle related fields. Use specifically for many to one serialized objects.

        :param field: field to check
        :param prefix: path to add field on related fields
        :param to_prefetch: if need to add field in prefetch related field list
        :return: sets contains select and prefetch related fields
        """
        return field.child


class SimpleSerializerAutoOptimizer(ManyRelationAutoOptimizer):
    def get_serializer(self, field: object):
        """
        Method to check and handle related fields. Use specifically for one to one serialized object.

        :param field: field to check
        :param prefix: path to add field on related fields
        :param to_prefetch: if need to add field in prefetch related field list
        :return: sets contains select and prefetch related fields
        """
        return field


class AsymetricRelatedFieldAutoOptimizer(ManyRelationAutoOptimizer):
    def get_serializer(self, field: object):
        """
        Method to check and handle related fields. Use specifically for asymetric fields.

        :param field: field to check
        :param prefix: path to add field on related fields
        :param to_prefetch: if need to add field in prefetch related field list
        :return: sets contains select and prefetch related fields
        """
        return field.serializer_class()


class ManyRelatedFieldAutoOptimizer(ManyRelationAutoOptimizer):
    def get_serializer(self, field: object):
        """
        Method to check and handle related fields. Use specifically for many related fields.

        :param field: field to check
        :param prefix: path to add field on related fields
        :param to_prefetch: if need to add field in prefetch related field list
        :return: sets contains select and prefetch related fields
        """

        if not hasattr(field.child_relation, "serializer_class"):
            return None
        return field.child_relation.serializer_class()


# ------------------- starter -------------------


class Optimizer(BaseOptimizer):
    """
    Class to optimize serializer fields. It will check if field is related or not and if it is related
    it will check if it is a simple field or a nested serializer. It will also check if field is in the list of fields
    to serialize and if it is in the list of fields to include.
    It used to fill select_related and prefetch_related fields in querysets.
    """

    def optimize(
        self, serializer: object, prefix: str, force_prefetch: bool
    ) -> tuple[set, set]:
        """
        Method to check and handle related field.

        Args:
            serializer: field or serializer to check
            prefix: path to add field on related fields
            force_prefetch: if need to add field in prefetch related field list
        Return:
            (tuple) sets contains select and prefetch related fields
        """
        prefetch_related_set = set()
        select_related_set = set()

        if not hasattr(serializer, "Meta"):
            return select_related_set, prefetch_related_set

        if not hasattr(serializer.Meta, "model"):
            return select_related_set, prefetch_related_set

        model_class = serializer.Meta.model
        on_demand_fields = getattr(serializer, "get_on_demand_fields", set)()
        fields_to_optimize = (
            (
                field_name,
                field,
                force_prefetch or self.check_if_prefetch_object(field),
            )
            for field_name, field in self.get_field_to_handle(
                serializer, on_demand_fields
            )
        )

        for field_name, field, to_prefetch in fields_to_optimize:
            optimizer = self.get_optimizer(field, field_name)
            if optimizer is None:
                continue

            select_fields, prefetch_fields = optimizer.optimize(
                field=field,
                prefix=prefix,
                model_class=model_class,
                to_prefetch=to_prefetch,
            )
            prefetch_related_set |= prefetch_fields
            select_related_set |= select_fields

        return select_related_set, prefetch_related_set

    def run(
        self, serializer: object, prefix: str, force_prefetch: bool = False
    ) -> tuple[set, set]:
        """
        Entry point of auto optimizer. It will check and handle related fields.
        It will return select and prefetch fields.

        Args:
            serializer (serializer): base serializer
            prefix (str): base prefix to add field on related fields
            force_prefetch (bool): if prefetch is needed, defaults to False
        Return:
            (tuple) sets contains select and prefetch related fields
        """
        select_fields, prefetch_fields = self.optimize(
            serializer, prefix, force_prefetch
        )
        select_fields = self.clean_fields(prefetch_fields, select_fields)
        _logger.debug(f"Select related fields: {select_fields}")
        _logger.debug(f"Prefetch related fields: {prefetch_fields}")
        return select_fields, prefetch_fields

    def __call__(self, *args, **kwds):
        return self.run(*args, **kwds)
