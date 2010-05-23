from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
import os
import models
from twidao import MainPage, SignupPage, SettingPage, AvatarsHandler, NotFoundPage, UserPage, StatusPage, ActionHandler, FavoritesPage, RepliesPage, DirectsPage

# Copyright (C) 2010-2012 vvoody <ydoovv@gmail.com>
# Souce codes licensed under GPLv3, see LICENSE.

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/signup', SignupPage),
                                      ('/setting', SettingPage),
                                      ('/avatar/([^/]*)', AvatarsHandler),
                                      ('/avatar/(.*)/(.*)', AvatarsHandler),
                                      ('/notfound', NotFoundPage),
                                      ('/status/(\w+)/([0-9]+)', StatusPage),
                                      ('/favorites', FavoritesPage),
                                      ('/replies', RepliesPage),
                                      ('/directs', DirectsPage),
                                      ('/(follow|unfollow)/(\w+)',ActionHandler),
                                      ('/(del|fav|unfav)/(\d+)', ActionHandler),
                                      ('/(\w+)', UserPage),
                                      ('/.*', NotFoundPage),], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
