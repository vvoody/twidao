from google.appengine.ext import db

class Members(db.Model):
    user = db.UserProperty()        # users.get_current_user()
    username = db.StringProperty()  # unique in this site, immutable(/signup)
    fullname = db.StringProperty()  # editable later(/setting)
    bio = db.StringProperty()
    following = db.StringListProperty(indexed=False)
    followers = db.StringListProperty(indexed=False)

# ancestor(Members)
class Tweets(db.Model):
    content = db.StringProperty()
    bywho = db.StringProperty()
    when = db.DateTimeProperty(auto_now_add=True)
    reply_to_tweet = db.IntegerProperty()
    reply_to = db.StringProperty()
    # used for get the tweet directly not set the ancestor
    tid = db.IntegerProperty()

# ancestor(Members)
class Counters(db.Model):
    tweets_counter = db.IntegerProperty(default=0)
    favorites_counter = db.IntegerProperty(default=0)
    following_counter = db.IntegerProperty(default=0)
    followers_counter = db.IntegerProperty(default=0)

# ancestor(Members)
class Replies(db.Model):
    # t = Replies(parent=some_user.key(), tweet = some_tweet.key())
    tweet = db.ReferenceProperty(Tweets)

# ancestor(Members)
class Favorites(db.Model):
    # f = Favorites(parent=some_user.key(), tweet = some_tweet.key())
    tweet = db.ReferenceProperty(Tweets)

# ancestor(Members)
# GET my timeline:
# TimelineQueue.all().ancestor(user).filter('active', True).order('-when')
# UNFOLLOW someone
# TimelineQueue.all().ancestor(user).filter('bywho', sb_unfollowed).active = False
class TimelineQueue(db.Model):
    tweet = db.ReferenceProperty(Tweets)
    bywho = db.StringProperty()
    active = db.BooleanProperty(default=True)  # remove from timeline
    faved = db.BooleanProperty(default=False)
    when  = db.DateTimeProperty()

# auto increment_counter of tweet id
class SysCounters(db.Model):
    counter = db.IntegerProperty(default=0)

# key_name -> username+size like 'katenormal'
class Avatars(db.Model):
    content = db.BlobProperty()
