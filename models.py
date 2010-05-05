from google.appengine.ext import db

class Members(db.Model):
    user = db.UserProperty()        # users.get_current_user()
    username = db.StringProperty()  # unique in this site, immutable(/signup)
    fullname = db.StringProperty()  # editable later(/setting)
    bio = db.StringProperty()
    following = db.StringListProperty(indexed=False)
    followers = db.StringListProperty(indexed=False)
    tweets_counter = db.IntegerProperty(default=0)
    following_counter = db.IntegerProperty(default=0)
    followers_counter = db.IntegerProperty(default=0)

class Tweets(db.Model):
    content = db.TextProperty()
    bywho = db.StringProperty()
    when = db.DateTimeProperty(auto_now_add=True)
    reply_to_tweet = db.IntegerProperty()
    reply_to = db.StringProperty()

class Replies(db.Model):
    # t = Replies(parent=some_user.key(), tweet = some_tweet.key())
    tweet = db.ReferenceProperty(Tweets)

class Favorites(db.Model):
    # f = Favorites(parent=some_user.key(), tweet = some_tweet.key())
    tweet = db.ReferenceProperty(Tweets)

class SysCounters(db.Model):
    counter = db.IntegerProperty(default=0)

# key_name -> username+size like 'katenormal'
class Avatars(db.Model):
    content = db.BlobProperty()
