#coding: utf-8

import datetime

from django.db import models

from django_history.current_context import CurrentUserField
from django_history.manager import HistoryDescriptor

import cPickle as pickle
from copy import copy
from django.utils.functional import curry
from django.utils.encoding import force_unicode
from django.core.exceptions import ObjectDoesNotExist

def revert_changes(model, self, field = None):
    pk_value = getattr(self, model._meta.pk.name)
    instance = model._default_manager.get(pk = pk_value)
    data = self.get_data()
    if data:
        if field: #откат одного поля
            assert (field in data)
            setattr(instance, field, data[field][0])
            del data[field]
        else:
            for attr, (old, __) in data.iteritems():
                setattr(instance, attr, old)
            data = {}
            
        instance.save()
        
        item = instance.history.latest()
        item.is_reverting = True
        item.save()
        
        #удаляем объект истории если все было откатано
        if not data: self.delete()
        else:
            self.set_data(data) #сохраняем только не откатанные данные
            self.save()
            
def verbose_value(field, value):
    if isinstance(field, models.BooleanField):
        return 'Да' if value else 'Нет'
    elif type(field) in (models.IntegerField, models.PositiveIntegerField, models.CharField):
        if field._choices:
            return force_unicode(dict(field.flatchoices).get(value, value), strings_only=True)
        else:
            return value
    return unicode(value) if value is not None else ''
            
def get_info(model, self, prefix = None):
    full_name = self.history_user.userprofile.full_name if self.history_user else ''
    date = self.history_date
    result = []
    prefix = prefix + ', ' if prefix else ''
    for attr, (old, new) in self.get_data().iteritems():
        if '_id' in attr:
            field = model._meta.get_field(attr.replace('_id', ''))
            if isinstance(field, models.ForeignKey):
                try:
                    old1 = field.rel.to._default_manager.get(pk = old) if old else old
                    new1 = field.rel.to._default_manager.get(pk = new) if new else new
                    new, old = new1, old1
                except ObjectDoesNotExist:
                    pass
        else:
            field = model._meta.get_field(attr)
            
        result.append({
            'operation': self.history_type,
            'id': self.pk,
            'user': full_name,
            'type': model._meta.module_name,
            'attr': attr,
            'attr_verbose': prefix + (field.verbose_name or 'undefined!'),
            'old': verbose_value(field, old),
            'new': verbose_value(field, new),
            'date': date,
            'is_reverting': self.is_reverting,
        })
    return result

class HistoricalRecords(object):
    registry = {} #register history models
    
    def __init__(self, exclude = None, include = None):
        self.exclude = exclude
        self.include = include
    
    def contribute_to_class(self, cls, name):
        self.manager_name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)

    def finalize(self, sender, **kwargs):
        history_model = self.create_history_model(sender)

        models.signals.pre_save.connect(self.pre_save, sender=sender, weak=False)
        models.signals.post_delete.connect(self.post_delete, sender=sender, weak=False)
        models.signals.post_save.connect(self.post_save, sender=sender, weak=False)

        descriptor = HistoryDescriptor(history_model)
        setattr(sender, self.manager_name, descriptor)

    def create_history_model(self, model):
        """
        Creates a historical model to associate with the model provided.
        """
        attrs = self.get_history_model_fields(model)
        attrs.update(Meta=type('Meta', (), self.get_meta_options(model)))
        name = 'Historical%s' % model._meta.object_name
        history_model =  type(name, (models.Model,), attrs)
        self.__class__.registry[model._meta.module_name] = history_model
        return history_model
    
    def __contains__(self, module_name):
        return module_name in self.__class__.registry
    
    def get_history_model(self, module_name):
        return self.__class__.registry.get(module_name)

    def get_history_model_fields(self, model):
        """
        Returns a dictionary of fields that will be added to the historical
        record model, in addition to the ones returned by copy_fields below.
        """
        rel_nm = '_%s_history' % model._meta.object_name.lower()
        fields =  {
            '__module__': model.__module__,
            
            #fields of history item
            'history_id': models.AutoField(primary_key=True),
            'history_date': models.DateTimeField(default=datetime.datetime.now),
            'history_user': CurrentUserField(related_name=rel_nm),
            'history_data': models.TextField(), #here is only the changed data
            'history_all_data': models.TextField(blank = True, null = True), #here saved all data of item
            'history_type': models.CharField(max_length=1, choices=(
                ('+', 'Created'),
                ('~', 'Changed'),
                ('-', 'Deleted'),
            )),
            'is_reverting': models.BooleanField(default = False),
            
            #method of history item
            'revert': curry(revert_changes, model),
            'get_info': curry(get_info, model),
            'get_data': lambda self: pickle.loads(self.history_data.encode('utf-8')),
            'set_data': lambda self, data: setattr(self, 'data', pickle.dumps(data)),
            '__unicode__': lambda self: u'%s by %s on %s, %s' % (self.get_history_type_display(), 
                                                                 self.history_user, self.history_date, 
                                                                 self.get_data())
        }
        
        #primary key that point to the main object
        pk_field = copy(model._meta.get_field(model._meta.pk.name))
        pk_field.__class__ = models.IntegerField
        pk_field._unique = False
        pk_field.primary_key = False
        pk_field.db_index = True
        
        fields[model._meta.pk.name] = pk_field
        return fields

    def get_meta_options(self, model):
        """
        Returns a dictionary of fields that will be added to
        the Meta inner class of the historical record model.
        """
        return {
            'ordering': ('-history_date',),
            'get_latest_by': 'history_date',
        }

    def pre_save(self, instance, **kwargs):
        if instance.pk:
            self.create_historical_record(instance, '~')
        
    def post_save(self, instance, created, **kwargs):
        if created:
            self.create_historical_record(instance, '+')

    def post_delete(self, instance, **kwargs):
        self.create_historical_record(instance, '-')

    def create_historical_record(self, instance, history_type):
        manager = getattr(instance, self.manager_name)
        
        attrs = {}
        attrs[instance._meta.pk.name] = getattr(instance, instance._meta.pk.name)
        #collecting changed fields
        history_data = {}
        history_all_data = {}
        if instance.pk and history_type != '-':
            old = instance.__class__._default_manager.get(pk = instance.pk)
            for field in instance._meta.fields:
                if (self.exclude and field.name in self.exclude) or (self.include and field.name not in self.include):
                    continue
                                
                if field.editable and type(field) not in (models.ManyToManyField, ):
                    new_value = getattr(instance, field.attname)
                    old_value = getattr(old, field.attname)
                    
                    history_all_data[field.attname] = new_value
                    
                    if new_value != old_value:
                        history_data[field.attname] = (old_value, new_value)
                        
        manager.create(history_type=history_type, 
                       history_data = pickle.dumps(history_data),
                       history_all_data = pickle.dumps(history_all_data), 
                       **attrs)


class FullHistoricalRecords(object):
    registry = {}  # register history models

    def __init__(self, register_in_admin=False):
        self.register_in_admin = register_in_admin

    def contribute_to_class(self, cls, name):
        self.manager_name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)

    def finalize(self, sender, **kwargs):
        history_model = self.create_history_model(sender)

        # The HistoricalRecords object will be discarded,
        # so the signal handlers can't use weak references.
        models.signals.post_save.connect(self.post_save, sender=sender,
                                         weak=False)
        models.signals.post_delete.connect(self.post_delete, sender=sender,
                                           weak=False)

        descriptor = HistoryDescriptor(history_model)
        setattr(sender, self.manager_name, descriptor)

        if self.register_in_admin:
            from django.contrib import admin
            admin.site.register(history_model)

    def create_history_model(self, model):
        """
        Creates a historical model to associate with the model provided.
        """
        attrs = self.copy_fields(model)
        attrs.update(self.get_extra_fields(model))
        attrs.update(Meta=type('Meta', (), self.get_meta_options(model)))
        name = 'FullHistorical%s' % model._meta.object_name
        history_model = type(name, (models.Model,), attrs)
        self.__class__.registry[model._meta.module_name] = history_model
        return history_model

    def copy_fields(self, model):
        """
        Creates copies of the model's original fields, returning
        a dictionary mapping field name to copied field object.
        """
        # Though not strictly a field, this attribute
        # is required for a model to function properly.
        fields = {'__module__': model.__module__}

        for field in model._meta.fields:
            field = copy(field)

            if isinstance(field, models.AutoField):
                # The historical model gets its own AutoField, so any
                # existing one must be replaced with an IntegerField.
                field.__class__ = models.IntegerField
            if isinstance(field, models.OneToOneField):
                field.__class__ = models.ForeignKey

            if field.primary_key or field.unique:
                # Unique fields can no longer be guaranteed unique,
                # but they should still be indexed for faster lookups.
                field.primary_key = False
                field._unique = False
                field.db_index = True
            fields[field.name] = field

        return fields

    def get_extra_fields(self, model):
        """
        Returns a dictionary of fields that will be added to the historical
        record model, in addition to the ones returned by copy_fields below.
        """
        rel_nm = '_%s_history' % model._meta.object_name.lower()
        return {
            'history_id': models.AutoField(primary_key=True),
            'history_date': models.DateTimeField(default=datetime.datetime.now),
            'history_user': CurrentUserField(related_name=rel_nm),
            'history_type': models.CharField(max_length=1, choices=(
                ('+', 'Created'),
                ('~', 'Changed'),
                ('-', 'Deleted'),
            )),
            'history_object': HistoricalObjectDescriptor(model),
            '__unicode__': lambda self: u'%s на %s' % (self.history_object,
                                                          self.history_date.strftime('%d.%m.%Y %H:%M'))
        }

    def get_meta_options(self, model):
        """
        Returns a dictionary of fields that will be added to
        the Meta inner class of the historical record model.
        """
        return {
            'ordering': ('-history_date',),
            'verbose_name': u'История: %s' % model._meta.verbose_name,
            'verbose_name_plural': u'История: %s' % model._meta.verbose_name_plural
        }

    def post_save(self, instance, created, **kwargs):
        self.create_historical_record(instance, created and '+' or '~')

    def post_delete(self, instance, **kwargs):
        self.create_historical_record(instance, '-')

    def create_historical_record(self, instance, type):
        manager = getattr(instance, self.manager_name)
        attrs = {}
        for field in instance._meta.fields:
            attrs[field.attname] = getattr(instance, field.attname)
        manager.create(history_type=type, **attrs)


class HistoricalObjectDescriptor(object):
    def __init__(self, model):
        self.model = model

    def __get__(self, instance, owner):
        values = (getattr(instance, f.attname) for f in self.model._meta.fields)
        return self.model(*values)
