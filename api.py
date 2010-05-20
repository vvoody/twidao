from google.appengine.ext import db
#from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
import models
import StringIO

# Copyright (C) 2010-2012 vvoody <ydoovv@gmail.com>
# Souce codes licensed under GPLv3, see LICENSE.

class NotFound(webapp.RequestHandler):
    def get(self):
        self.error(404)

class StatusPublictimeline(webapp.RequestHandler):
    def get(self):
        q = models.Tweets.all().order('-when')
        tweets = q.fetch(20)
        if tweets:
            output = StringIO.StringIO()
            for t in tweets:
                output.write(t.to_xml())
            self.response.out.write(output.getvalue())
            output.close()
        else:
            self.error(404)

class StatusSingle(webapp.RequestHandler):
    def get(self, tweet_id):
        tweet = models.Tweets.all().filter('tid', int(tweet_id)).get()
        if tweet:
            self.response.out.write(tweet.to_xml())
        else:
            self.error(404)

application = webapp.WSGIApplication([('/api/status/public_timeline', StatusPublictimeline),
                                      ('/api/status/(\d+)', StatusSingle),
                                      ('/.*', NotFound),], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
