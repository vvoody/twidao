from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
import os
import models
from twidao import MainPage, SignupPage, SettingPage, AvatarsHandler, NotFoundPage

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/signup', SignupPage),
                                      ('/setting', SettingPage),
                                      ('/avatar/([^/]*)', AvatarsHandler),
                                      ('/avatar/(.*)/(.*)', AvatarsHandler),
                                      ('/notfound', NotFoundPage)], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
