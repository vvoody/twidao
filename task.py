from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import images
import models

class ResizeAvatar(webapp.RequestHandler):
    """Resize the avatar image file uploaded to smaller and much smaller size.
    """
    def get(self):
        username = self.request.get('username')
        avatar_origin = models.Avatars.get_by_key_name(username + 'origin')
        if avatar_origin:
            img = images.Image(avatar_origin.content)
            img.resize(width=73, height=73)
            #img.im_feeling_lucky()
            avatar_bigger = models.Avatars(key_name=username+"bigger",
                                           content=img.execute_transforms())
            avatar_bigger.put()
            img.resize(width=48, height=48)
            avatar_normal = models.Avatars(key_name=username+"normal",
                                           content=img.execute_transforms())
            avatar_normal.put()
            #self.response.headers['Content-Type'] = 'image'
            #self.response.out.write(avatar_origin.content)

class PushTimeline(webapp.RequestHandler):
    """Push the new tweet just posted to followers' timeline queue
    """
    def get(self):
        tid = int(self.request.get('tid'))
        tuser = self.request.get('user').lower()
        ancestor = models.Members.get_by_key_name(tuser)
        tweet = models.Tweets.get_by_id(tid, ancestor)
        #self.response.out.write("%s" % tweet.content)
        if not tweet:
            pass
        else:
            #self.response.out.write("%s" % followers)
            followers = ancestor.followers  # unicode object
            for follower in followers:
                ancestor = models.Members.get_by_key_name(str(follower))
                models.TimelineQueue(parent=ancestor,
                                     tweet = tweet.key(),
                                     bywho = tuser,
                                     when  = tweet.when,
                                     ).put()
            # end

application = webapp.WSGIApplication([('/task/avatar/resize', ResizeAvatar),
                                      ('/task/tweets/push_timeline', PushTimeline),
                                      ], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
