from importlib import import_module

from rest_framework import serializers
from .serializers import pass_context


class AsymetricRelatedField(serializers.PrimaryKeyRelatedField):
    """
    Class for asymetric representation of data. Used `PrimaryKeyReladedField` for parent.
    With this, we can use id in POST and have serialized data in GET.
    """

    def __init__(self, serializer_class, *args, **kwargs):
        """
        :param serializer_class: serializer for data representation. Can be string or serializer class.
        If it's string, set absolute path of the serializer class.
        :param serializer_kwargs: set it if serializer_class need parameters, defaults to None
        """
        self.__serializer_class = serializer_class
        super().__init__(*args, **kwargs)

    @property
    def serializer_class(self):
        serializer_class = self.__serializer_class
        if isinstance(self.__serializer_class, str):
            serializer_class = self._get_serializer_class()
        return serializer_class

    def to_representation(self, value):
        """
        Overwrite method `to_representation()` to use serializer class for data representation.
        Pass context to serializer for using dynamic fields.
        """
        if self.context != {} and self.field_name_in_context():
            return self._internal_representation(
                value, pass_context(self.field_name, self.context)
            ).data
        if not isinstance(value, dict):
            return value.pk
        return value["pk"]

    def get_queryset(self):
        """
        PrimaryKeyRelatedField serializer must be instanciate with a queryset (or read_only=True).
        We override the `get_queryset()` method to allow user not to give a queryset when instanciating
        this class. The queryset is automatically generated from given serializer_class.
        """
        if self.queryset:
            return self.queryset
        return self.serializer_class.Meta.model.objects.all()

    def get_choices(self, cutoff=None):
        """
        Overwrite to fix drf autodoc, to set `item.pk` in place of `to_representation()`.
        :param cutoff: use to split the queryset end, defaults to None
        """
        queryset = self.get_queryset()
        if queryset is None:
            return {}

        if cutoff is not None:
            queryset = queryset[:cutoff]

        # The override is here : item.pk in place of self.to_representation(item)
        return {item.pk: self.to_representation(item) for item in queryset}

    def use_pk_only_optimization(self):
        """Overwrite for reactive all fields validation for reading."""
        return not (self.context != {} and self.field_name_in_context())

    @property
    def field_name(self):
        return self.field_name if self.field_name != "" else self.parent.field_name

    def field_name_in_context(self):
        query_params = self.context["request"].query_params
        return self.field_name in query_params.get("include_fields", [])

    def _internal_representation(self, value, context):
        return self.serializer_class(value, context=context, **self.serializer_kwargs)

    def _get_serializer_class(self):
        """
        Method to import serializer class if path of this class is set.
        Trick to add "lazy" import of serializer class.
        """
        splited_serializer_name = self.__serializer_class.split(".")
        serializer_name = splited_serializer_name[-1]
        module_path = ".".join(splited_serializer_name[:-1])
        module = import_module(module_path)
        return getattr(module, serializer_name)
