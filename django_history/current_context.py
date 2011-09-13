#coding: utf-8

from django.db import models
from django.db.models import signals
from django.utils.functional import curry
from django.utils.decorators import decorator_from_middleware
from django.contrib.auth.models import User

class FieldRegistry(object):
    _registry = {}

    def add_field(self, model, field):
        reg = self.__class__._registry.setdefault(model, [])
        reg.append(field)

    def get_fields(self, model):
        return self.__class__._registry.get(model, [])

    def __contains__(self, model):
        return model in self.__class__._registry

class CurrentUserMiddleware(object):
    def process_request(self, request):
        if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            # This request shouldn't update anything,
            # so no singal handler should be attached.
            return
            
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated() else None

        update_context = curry(self.update_context, user)
        signals.pre_save.connect(update_context, dispatch_uid=request, weak=False)

    def update_context(self, user, sender, instance, **kwargs):
        registry = FieldRegistry()
        if sender in registry:
            for field in registry.get_fields(sender):
                if field.one_time and getattr(instance, field.name, None): 
                    continue
                
                if isinstance(field, CurrentUserField):
                    setattr(instance, field.name, user)

    def process_response(self, request, response):
        signals.pre_save.disconnect(dispatch_uid=request)
        return response
    
record_current_context = decorator_from_middleware(CurrentUserMiddleware)
    
class CurrentUserField(models.ForeignKey):
    def __init__(self, one_time = False, **kwargs):
        self.one_time = one_time
        super(CurrentUserField, self).__init__(User, null=True, **kwargs)

    def contribute_to_class(self, cls, name):
        super(CurrentUserField, self).contribute_to_class(cls, name)
        registry = FieldRegistry()
        registry.add_field(cls, self)
        
try:
    from south.modelsinspector import add_introspection_rules
    
    ## south rules
    user_rules = [(                                          
        (CurrentUserField,),                        
        [],                                             
        {                                               
            'to': ['rel.to', {'default': User}],        
            'null': ['null', {'default': True}],        
        },                                              
    )]
    
    add_introspection_rules(user_rules, ["^history\.current_context\.CurrentUserField"])
except:
    pass
