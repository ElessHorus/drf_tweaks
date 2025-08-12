from unittest.mock import MagicMock

from django.db.models.fields import related_descriptors

import pytest
from rest_framework.serializers import (
    ListSerializer,
    ManyRelatedField,
    PrimaryKeyRelatedField,
    Serializer,
    SerializerMethodField,
)

from drf_tweaks.optimizator import (
    BaseOptimizer,
    ListSerializerAutoOptimizer,
    ManyRelatedFieldAutoOptimizer,
    PrimaryKeyRelatedFieldAutoOptimizer,
    SerializerMethodFieldAutoOptimizer,
    SimpleSerializerAutoOptimizer,
    SourceSerializerAutoOptimizer,
)
# from api.commons.serializers import AsymetricRelatedField


@pytest.fixture
def base_optimizer():
    return BaseOptimizer(only_fields=set(), include_fields=set())


@pytest.mark.utils
def test_get_optimizer_source_serializer(base_optimizer):
    field = MagicMock()
    field.source = "some.source"
    field_name = "some_field"
    result = base_optimizer.get_optimizer(field, field_name)
    assert isinstance(result, SourceSerializerAutoOptimizer)


@pytest.mark.utils
def test_get_optimizer_primary_key_related_field(base_optimizer):
    field = PrimaryKeyRelatedField(queryset=MagicMock())
    field.source = "some_source"
    field_name = "some_field"
    result = base_optimizer.get_optimizer(field, field_name)
    assert isinstance(result, PrimaryKeyRelatedFieldAutoOptimizer)


# @pytest.mark.utils
# def test_get_optimizer_asymetric_related_field(base_optimizer):
#     field = AsymetricRelatedField(MagicMock, queryset=MagicMock())
#     field.source = "some_source"
#     field_name = "some_field"
#     result = base_optimizer.get_optimizer(field, field_name)
#     assert isinstance(result, AsymetricRelatedFieldAutoOptimizer)


@pytest.mark.utils
def test_get_optimizer_serializer_method_field(base_optimizer):
    field = SerializerMethodField()
    field.source = "some_source"
    field_name = "some_field"
    result = base_optimizer.get_optimizer(field, field_name)
    assert isinstance(result, SerializerMethodFieldAutoOptimizer)


@pytest.mark.utils
def test_get_optimizer_list_serializer(base_optimizer):
    field = ListSerializer(child=MagicMock())
    field.source = "some_source"
    field_name = "some_field"
    result = base_optimizer.get_optimizer(field, field_name)
    assert isinstance(result, ListSerializerAutoOptimizer)


@pytest.mark.utils
def test_get_optimizer_simple_serializer(base_optimizer):
    field = Serializer()
    field.source = "some_source"
    field_name = "some_field"
    result = base_optimizer.get_optimizer(field, field_name)
    assert isinstance(result, SimpleSerializerAutoOptimizer)


@pytest.mark.utils
def test_get_optimizer_many_related_field(base_optimizer):
    field = ManyRelatedField(child_relation=MagicMock())
    field.source = "some_source"
    field_name = "some_field"
    result = base_optimizer.get_optimizer(field, field_name)
    assert isinstance(result, ManyRelatedFieldAutoOptimizer)


@pytest.mark.utils
def test_check_if_related_object(base_optimizer):
    model_field = MagicMock(spec=related_descriptors.ForwardManyToOneDescriptor)
    assert base_optimizer.check_if_related_object(model_field) is True

    model_field = MagicMock(spec=related_descriptors.ReverseOneToOneDescriptor)
    assert base_optimizer.check_if_related_object(model_field) is True

    model_field = MagicMock()
    assert base_optimizer.check_if_related_object(model_field) is False


@pytest.mark.utils
def test_check_if_prefetch_object(base_optimizer):
    model_field = MagicMock(spec=related_descriptors.ManyToManyDescriptor)
    assert base_optimizer.check_if_prefetch_object(model_field) is True

    model_field = MagicMock(spec=related_descriptors.ReverseManyToOneDescriptor)
    assert base_optimizer.check_if_prefetch_object(model_field) is True

    model_field = MagicMock()
    assert base_optimizer.check_if_prefetch_object(model_field) is False


@pytest.mark.utils
def test_filter_field_name(base_optimizer):
    field_name = "test_field"
    fields_to_serialize = ["test_field__test_field", "another_field"]
    assert base_optimizer.filter_field_name(field_name, fields_to_serialize) == {
        "test_field"
    }

    field_name = "non_existent_field"
    assert base_optimizer.filter_field_name(field_name, fields_to_serialize) == set()

    fields_to_serialize = None
    assert base_optimizer.filter_field_name(field_name, fields_to_serialize) is None


@pytest.mark.utils
def test_clean_fields(base_optimizer):
    prefetch_set = {"field1", "field2"}
    select_set = {"field2", "field3"}
    select_set = base_optimizer.clean_fields(prefetch_set, select_set)
    assert select_set == {"field3"}


@pytest.mark.utils
def test_check_in_fields(base_optimizer):
    model_class = MagicMock()
    model_field = MagicMock(spec=property)
    assert base_optimizer.check_in_fields(model_class, model_field) is False

    model_field = MagicMock(spec=related_descriptors.ReverseOneToOneDescriptor)
    model_field.related = "related_field"
    model_class._meta.get_fields.return_value = ["related_field"]
    assert base_optimizer.check_in_fields(model_class, model_field) is True

    model_field = MagicMock(spec=related_descriptors.ManyToManyDescriptor)
    model_field.field = "related_field"
    model_class._meta.get_fields.return_value = ["related_field"]
    assert base_optimizer.check_in_fields(model_class, model_field) is True

    model_field = MagicMock(spec=related_descriptors.ReverseManyToOneDescriptor)
    model_field.rel = "related_field"
    model_class._meta.get_fields.return_value = ["related_field"]
    assert base_optimizer.check_in_fields(model_class, model_field) is True

    model_field = MagicMock()
    assert base_optimizer.check_in_fields(model_class, model_field) is False
