from pyramid.security import Allow, Deny, Everyone, Authenticated, ALL_PERMISSIONS, DENY_ALL
from pyramid.security import remember, forget
from pyramid.httpexceptions import HTTPFound

from . import log
from .models import User, Group

#
# Pyramid ACL factories
#

def admin_only_acl(request):
    """Generate our admin-only ACL"""
    return  [(Allow, 'group:' + group, ALL_PERMISSIONS) for group in
             request.registry.settings['admin_packager_groups'].split()]


def packagers_allowed_acl(request):
    """Generate an ACL for update submission"""
    return [(Allow, 'group:' + group, ALL_PERMISSIONS) for group in
            request.registry.settings['mandatory_packager_groups'].split()] + \
           [DENY_ALL]


#
# OpenID views
#

def login(request):
    login_url = request.route_url('login')
    referrer = request.url
    if referrer == login_url:
        referrer = request.route_url('home')
    came_from = request.params.get('came_from', referrer)
    request.session['came_from'] = came_from
    oid_url = request.registry.settings['openid.provider']
    return HTTPFound(location=request.route_url('verify_openid',
                                                _query=dict(openid=oid_url)))


def logout(request):
    headers = forget(request)
    return HTTPFound(location=request.route_url('home'), headers=headers)


#
# openid.success_callback
#

def remember_me(context, request, info, *args, **kw):
    log.debug('remember_me(%s)' % locals())
    log.debug('request.params = %r' % request.params)
    endpoint = request.params['openid.op_endpoint']
    if endpoint != request.registry.settings['openid.provider']:
        log.warn('Invalid OpenID provider: %s' % endpoint)
        request.session.flash('Invalid OpenID provider. You can only use: %s' %
                              request.registry.settings['openid.provider'])
        return HTTPFound(location=request.route_url('home'))
    username = info['identity_url'].split('http://')[1].split('.')[0]
    log.debug('%s successfully logged in' % username)
    log.debug('groups = %s' % info['groups'])

    # Find the user in our database. Create it if it doesn't exist.
    db = request.db
    user = db.query(User).filter_by(name=username).first()
    if not user:
        user = User(name=username)
        db.add(user)
        db.flush()

    # See if they are a member of any important groups
    important_groups = request.registry.settings['important_groups'].split()
    for important_group in important_groups:
        if important_group in info['groups']:
            group = db.query(Group).filter_by(name=important_group).first()
            if not group:
                group = Group(name=important_group)
                db.add(group)
                db.flush()
            user.groups.append(group)

    headers = remember(request, username)
    came_from = request.session['came_from']
    del(request.session['came_from'])
    response = HTTPFound(location=came_from)
    response.headerlist.extend(headers)
    return response
