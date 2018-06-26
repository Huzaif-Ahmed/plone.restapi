# -*- coding: utf-8 -*-
from Acquisition import aq_base
from Acquisition import aq_parent
from DateTime import DateTime
from plone.app.content.interfaces import INameFromTitle
from plone.app.uuid.utils import uuidToObject
from plone.uuid.interfaces import IUUID
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import base_hasattr
from random import randint
from zExceptions import Unauthorized
from zope.component import getUtility
from zope.component.interfaces import IFactory
from zope.container.contained import notifyContainerModified
from zope.container.contained import ObjectAddedEvent
from zope.container.interfaces import INameChooser
from zope.event import notify

import transaction


def create(container, type_, id_=None, title=None):
    """Create a new content item."""

    # Generate a temporary id if the id is not given
    if not id_:
        now = DateTime()
        new_id = '{}.{}.{}{:04d}'.format(
            type_.lower().replace(' ', '_'),
            now.strftime('%Y-%m-%d'),
            str(now.millis())[7:],
            randint(0, 9999))
    else:
        if isinstance(id_, unicode):
            new_id = id_.encode('utf8')
        else:
            new_id = id_

    portal_types = getToolByName(container, 'portal_types')
    type_info = portal_types.getTypeInfo(type_)

    # Check for add permission
    if not type_info.isConstructionAllowed(container):
        raise Unauthorized('Cannot create %s' % type_info.getId())

    # Check if allowed subobject type
    container_type_info = portal_types.getTypeInfo(container)
    if not container_type_info.allowType(type_):
        raise Unauthorized('Disallowed subobject type: %s' % type_)

    # Check for type constraints
    if type_ not in [fti.getId() for fti in container.allowedContentTypes()]:
        raise Unauthorized('Disallowed subobject type: %s' % type_)

    if type_info.product:
        # Oldstyle factory
        factory = type_info._getFactoryMethod(container, check_security=0)
        new_id = factory(new_id, title=title)
        obj = container._getOb(new_id)

    else:
        factory = getUtility(IFactory, type_info.factory)
        obj = factory(new_id, title=title)

    if base_hasattr(obj, '_setPortalTypeName'):
        obj._setPortalTypeName(type_info.getId())

    return obj


def add(container, obj):
    """Add an object to a container."""
    id_ = obj.getId()
    # Archetypes objects are already created in a container thus we just fire
    # the notification events.
    if aq_base(container) is aq_base(aq_parent(obj)):
        notify(ObjectAddedEvent(obj, container, id_))
        notifyContainerModified(container)
        return obj
    else:
        new_id = container._setObject(id_, obj)
        # _setObject triggers ObjectAddedEvent which can end up triggering a
        # content rule to move the item to a different container. In this case
        # look up the object by UUID.
        try:
            return container._getOb(new_id)
        except AttributeError:
            uuid = IUUID(obj)
            return uuidToObject(uuid)


def rename(obj):
    """Rename an object if it has a temporary id."""

    # Archetypes objects may get renamed during deserialization.
    # Do not rename again.
    if (base_hasattr(obj, '_isIDAutoGenerated') and
            not obj._isIDAutoGenerated(obj.getId())):
        return

    container = aq_parent(obj)
    chooser = INameChooser(container)
    # INameFromTitle adaptable objects should not get a name
    # suggestion. NameChooser would prefer the given name instead of
    # the one provided by the INameFromTitle adapter.
    suggestion = None
    name_from_title = INameFromTitle(obj, None)
    if name_from_title is None:
        if base_hasattr(obj, 'generateNewId'):
            suggestion = obj.generateNewId()
        else:
            suggestion = obj.Title()
    name = chooser.chooseName(suggestion, obj)
    transaction.savepoint(optimistic=True)
    container.manage_renameObject(obj.getId(), name)
