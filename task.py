from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import images
import models
import re

# Copyright (C) 2010-2012 vvoody <ydoovv@gmail.com>
# Souce codes licensed under GPLv3, see LICENSE.

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
                if tweet.reply_to == None or tweet.reply_to in ancestor.following:
                    models.TimelineQueue(parent=ancestor,
                                         tweet = tweet.key(),
                                         bywho = tuser,
                                         when  = tweet.when,
                                         ).put()
            # end

class RepliesHandler(webapp.RequestHandler):
    """Check whether tweet's reply_to_tweet & reply_to field are corrent or not,
    and find out who mentioned from the tweet.
    """
    def validate_reply_to(self, origin_tweet, reply_to_tweet_id, reply_to):
        ancestor = models.Members.get_by_key_name(reply_to)
        reply_to_tweet = models.Tweets.get_by_id(reply_to_tweet_id, ancestor)
        if origin_tweet.content.split(' ')[0][0] == '@':
            if origin_tweet.content.split(' ')[0][1:].lower() == reply_to_tweet.bywho:
                if reply_to_tweet.bywho == origin_tweet.reply_to:
                    return
                else:
                    origin_tweet.reply_to = reply_to_tweet.bywho
                    origin_tweet.put()
                    return
        origin_tweet.reply_to_tweet = None
        origin_tweet.reply_to = None
        origin_tweet.put()

    def findout_mentions(self, tweet):
        mention = map(lambda x: x.lower(),
                    re.findall(r'@([a-zA-Z0-9]*)', tweet.content))
        # push into Replies & TimelineQueue
        # RT @Rabit: I love you! (not a @Test) ^_^
        for user in mention:
            ancestor = models.Members.get_by_key_name(user)
            if ancestor:
                models.Replies(parent=ancestor, tweet=tweet).put()
        # End

    def get(self):
        tid = int(self.request.get('tid'))
        tuser = self.request.get('user').lower()
        ancestor = models.Members.get_by_key_name(tuser)
        tweet = models.Tweets.get_by_id(tid, ancestor)
        if tweet.reply_to_tweet != None:
            self.validate_reply_to(tweet, tweet.reply_to_tweet, tweet.reply_to)
        elif tweet.reply_to != None:  # reply to unknown tweet
            tweet.reply_to = None
            tweet.put()
        self.findout_mentions(tweet)

application = webapp.WSGIApplication([('/task/avatar/resize', ResizeAvatar),
                                      ('/task/tweets/push_timeline', PushTimeline),
                                      ('/task/tweets/replies', RepliesHandler),
                                      ], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
