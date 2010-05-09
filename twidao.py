from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.api.labs import taskqueue
import os
import models
from datetime import datetime

def increment_counter(counter_name, amount):
    obj = models.SysCounters.get_by_key_name(counter_name)
    obj.counter += amount
    obj.put()
    return obj.counter

def get_new_tweet_id():
    return int(db.run_in_transaction(increment_counter, 'tweet_id', 1))

class NotFoundPage(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates/notfound.html')
        self.response.out.write(template.render(path, {'notfound': 'notfound'}))

class MainPage(webapp.RequestHandler):
    def __init__(self):
        self.cur_user = users.get_current_user()
        self.user = models.Members.all().filter('user', self.cur_user).get()
        self.template_values = {}

    def render_page(self):
        path = os.path.join(os.path.dirname(__file__), 'templates/main.html')
        self.response.out.write(template.render(path, self.template_values))

    def show_public_timeline(self, next_page):
        # fetch Tweets
        q = models.Tweets.all().order('-when')
        if next_page:
            q.with_cursor(next_page)
        # Fetch next 20 tweets
        tweets = q.fetch(20)
        # Store the latest cursor for the next request.
        next_page = q.cursor()
        self.template_values = {'login_url': users.create_login_url('/'),
                                'pagetype': 'public timeline',
                                'tweets': tweets,
                                'page_size': len(tweets),
                                'next_page': next_page,
                                }
        self.render_page()
        #self.response.out.write("Public timeline...")

    def get(self):
        next_page = self.request.get('next_page')
        if not self.cur_user:
            self.show_public_timeline(next_page)
        elif not self.user:
            self.redirect('/signup')
        else:
            q = models.TimelineQueue.all().ancestor(self.user.key()).filter('active', True).order('-when')
            if next_page:
                q.with_cursor(next_page)
            res = q.fetch(20)
            tweets = db.get([t.tweet.key() for t in res])
            next_page = q.cursor()
            logout_url = users.create_logout_url('/')
            self.template_values = {'user': self.user,
                                    'logout_url': logout_url,
                                    'pagetype': 'my timeline',
                                    'tweets': tweets,
                                    'page_size': len(tweets),
                                    'next_page': next_page,
                                    }
            self.render_page()

    def store_tweet(self, content, bywho, reply_to_tweet, reply_to):
        def txn(tid, ancestor, content, bywho, reply_to_tweet, reply_to):
            # store the new tweet
            now = datetime.now()
            tkey = db.Key.from_path("Members", bywho, 'Tweets', tid)
            models.Tweets(key=tkey,
                          content = content,
                          bywho = bywho,
                          when = now,
                          reply_to_tweet = reply_to_tweet,
                          reply_to = reply_to,
                          tid = tid,
                          ).put()
            # increment tweets counter
            counter = models.Counters.all().ancestor(ancestor).get()
            counter.tweets_counter += 1
            counter.put()
            # add this tweet to the TimelineQueue immediately
            models.TimelineQueue(parent=ancestor,
                                 tweet= tkey,
                                 bywho= bywho,
                                 when=now,
                                 ).put()
        #
        tid = get_new_tweet_id()
        ancestor = self.user.key()
        db.run_in_transaction(txn, tid, ancestor, content, bywho, reply_to_tweet, reply_to)
        return tid

    def validator(self, *args):
        # 1. tweet, 2. reply_to_tweet, 3. reply_to
        if args[1] != '' and args[2] != '':
            return (args[0], int(args[1]), args[2])
        else:
            return (args[0], None, None)

    def post(self):
        if not self.user:
            self.error(401)
        self.response.out.write("%s" % (self.request.get('tweet')))
        tweet_content, reply_to_tweet, reply_to = self.validator(
            self.request.get('tweet'),
            self.request.get('reply_to_tweet'),
            self.request.get('reply_to'))
        # 1. get unique id & store in Tweets(with ancestor)
        # 2. Counters
        # 3.1 TimelineQueue, ancestor(self)
        # 1, 2 & 3.1 in the same transaction(cuz of same entity group / ancestor)
        #self.response.out.write("'%s', '%d', '%s'" % (tweet_content, reply_to_tweet, reply_to))
        username = self.user.username.lower()
        tid = self.store_tweet(tweet_content,
                               username,
                               reply_to_tweet,
                               reply_to)
        # 3.2 TimelineQueue, ancestor(followers) -> taskqueue
        # push the new tweet to followers' timeline queue
        taskqueue.Task(url='/task/tweets/push_timeline?tid=%d&user=%s' %
                       (tid, username),
                       method='GET',
                       ).add(queue_name='tweets')
        # 4. replies & find out the mentions of this tweet
        taskqueue.Task(url='/task/tweets/replies?tid=%d&user=%s' % (tid, username),
                       method='GET',
                       ).add(queue_name='tweets')
        # End of MainPage

# login: required
class SignupPage(webapp.RequestHandler):
    def __init__(self):
        self.cur_user = users.get_current_user()
        self.user = models.Members.all().filter('user', self.cur_user).get()

    def get(self):
        if self.user :  # registered (and same Google Account)
            self.redirect('/')
        logout_url = users.create_logout_url('/')
        template_values = {'user': 'signup',
                           'signup': 'signup',
                           'logout_url': logout_url,
                           'username': 'foobar'}
        path = os.path.join(os.path.dirname(__file__), 'templates/signup.html')
        self.response.out.write(template.render(path, template_values))

    def validator(self, *args):
        return args

    def register_member(self, username, fullname, bio):
        def store_to_Members(username, fullname, bio):
            obj = db.get(db.Key.from_path("Members", username.lower()))
            if not obj:
                obj = models.Members(key_name=username.lower(),  # unique and lower case
                                         user=self.cur_user,
                                         username=username,
                                         fullname=fullname,
                                         bio=bio,
                                         following=[],
                                         followers=[])
            else:
                # Username existed
                raise db.TransactionFailedError
            obj.put()
            return obj.key()
        #
        def connect_with_Counters(ancestor, username):
            counter = models.Counters(parent=ancestor, key_name=username.lower()+'counters')
            counter.put()
        #
        ancestor = db.run_in_transaction(store_to_Members, username, fullname, bio)
        db.run_in_transaction(connect_with_Counters, ancestor, username)

    def post(self):
        get_form = self.request.get
        username, fullname, bio = self.validator(get_form('username'),
                                                 get_form('fullname'),
                                                 get_form('bio'))
        try:
           self.register_member(username, fullname, bio)
        except db.TransactionFailedError:
            template_values = {'error':
                               "Username '%s' has been taken!" % username}
            path = os.path.join(os.path.dirname(__file__), 'templates/signup.html')
            self.response.out.write(template.render(path, template_values))
        else:
            self.redirect('/')

class SettingPage(webapp.RequestHandler):
    def __init__(self):
        self.cur_user = users.get_current_user()
        self.user = models.Members.all().filter('user = ', self.cur_user).get()

    def get(self):
        if not self.user:  # Not registered
            self.redirect('/signup')
        else:
            logout_url = users.create_logout_url('/')
            template_values = {'user': self.user,
                               'username': self.user.username,
                               'fullname': self.user.fullname,
                               'bio': self.user.bio,
                               'logout_url': logout_url}
            path = os.path.join(os.path.dirname(__file__), 'templates/setting.html')
            self.response.out.write(template.render(path, template_values))

    def validator(self, *args):
        return args

    def update_member(self, fullname, bio):
        u = models.Members.get_by_key_name(self.user.username)
        u.fullname, u.bio = fullname, bio
        u.put()
        #raise db.TransactionFailedError

    def upload_avator(self, avatar, size='origin'):
        a = models.Avatars(key_name=self.user.username + size,
                           content=avatar)
        a.put()

    def post(self):
        get_form = self.request.get
        fullname, bio = self.validator(get_form('fullname'), get_form('bio'))
        avatar = get_form('avatarfile')
        if avatar:
            db.run_in_transaction(self.upload_avator, avatar)
            # add task to resize-img queue
            taskqueue.Task(url='/task/avatar/resize?username=%s' % self.user.username,
                           method='GET',
                           ).add(queue_name='avatar')
        if self.user.fullname == fullname and self.user.bio == bio:
            self.redirect('/setting')
        try:
            db.run_in_transaction(self.update_member, fullname, bio)
        except db.TransactionFailedError:
            logout_url = users.create_logout_url('/')
            template_values = {'user': 'setting',
                               'username': self.user.username,
                               'fullname': self.user.fullname,
                               'bio': self.user.bio,
                               'logout_url': logout_url,
                               'error':"Oops... Try that again."}
            path = os.path.join(os.path.dirname(__file__), 'templates/setting.html')
            self.response.out.write(template.render(path, template_values))
        else:
            self.redirect('/setting')

# Deal with request like /avatar/john/bigger
class AvatarsHandler(webapp.RequestHandler):
    def get(self, username, size='normal'):
        username = username.lower()
        if size not in ('origin', 'bigger', 'normal'):
            self.redirect('/notfound')
        avatar = models.Avatars.get_by_key_name(username+size)
        if avatar:
            self.response.headers['Content-Type'] = 'image'
            self.response.out.write(avatar.content)
        # registered but not upload avatar yet
        elif models.Members.get_by_key_name(username):
            self.redirect('/static/default_avatar_%s.png' % size)
        else:
            self.redirect('/notfound')

# User page & their timeline
class UserPage(webapp.RequestHandler):
    def show_user_timeline(self, page_user, next_page):
        cur_user = users.get_current_user()
        user = models.Members.all().filter('user', cur_user).get()
        q = models.Tweets.all().ancestor(page_user.key()).order('-when')
        if next_page:
            q.with_cursor(next_page)
        tweets = q.fetch(20)
        next_page = q.cursor()
        followed = None
        if user:
            followed = True if page_user.username.lower() in user.following else \
                       False
        login_url = users.create_login_url('/')
        logout_url = users.create_logout_url('/')
        template_values = {'user': user, 'page_user': page_user,
                           'pagetype': 'user timeline',
                           'logout_url': logout_url, 'login_url': login_url,
                           'tweets': tweets,'followed': followed,
                           'page_size': len(tweets),'next_page': next_page,
                           }
        path = os.path.join(os.path.dirname(__file__), 'templates/main.html')
        self.response.out.write(template.render(path, template_values))

    def get(self, username):
        page_user = models.Members.get_by_key_name(username.lower())
        if not page_user:
            self.redirect('/notfound')
        else:
            self.show_user_timeline(page_user, self.request.get('next_page'))
        # End UserPage

class StatusPage(webapp.RequestHandler):
    def get(self, username, tweet_id):
        tuser = models.Members.get_by_key_name(username.lower())
        tweet = models.Tweets.get_by_id(int(tweet_id), parent=tuser.key())
        if not tweet:
            self.redirect('/notfound')
        else:
            cur_user = users.get_current_user()
            login_user = models.Members.all().filter('user', cur_user).get()
            login_url = users.create_login_url('/')
            logout_url = users.create_logout_url('/')
            template_values = {'user': login_user,
                               'logout_url': logout_url, 'login_url': login_url,
                               'tweet': tweet,
                               }
            path = os.path.join(os.path.dirname(__file__), 'templates/status.html')
            self.response.out.write(template.render(path, template_values))

class FavoritesPage(webapp.RequestHandler):
    def show_user_favorites(self, user, next_page):
        q = models.Favorites.all().ancestor(user.key())
        if next_page:
            q.with_cursor(next_page)
        res = q.fetch(20)
        tweets = db.get([t.tweet.key() for t in res])
        next_page = q.cursor()
        login_url = users.create_login_url('/')
        logout_url = users.create_logout_url('/')
        template_values = {'user': user,
                           'pagetype': 'user favorites',
                           'logout_url': logout_url, 'login_url': login_url,
                           'tweets': tweets,
                           'page_size': len(tweets),'next_page': next_page,
                           }
        path = os.path.join(os.path.dirname(__file__), 'templates/favorites.html')
        self.response.out.write(template.render(path, template_values))

    def get(self):
        cur_user = users.get_current_user()
        user = models.Members.all().filter('user', cur_user).get()
        if not user:
            login_url = users.create_login_url('/favorites')
            self.redirect(login_url)
        else:
            self.show_user_favorites(user, self.request.get('next_page'))

# login: required
class RepliesPage(webapp.RequestHandler):
    def show_user_replies(self, user, next_page):
        q = models.Replies.all().ancestor(user.key())
        if next_page:
            q.with_cursor(next_page)
        res = q.fetch(20)
        tweets = db.get([t.tweet.key() for t in res])
        next_page = q.cursor()
        login_url = users.create_login_url('/')
        logout_url = users.create_logout_url('/')
        template_values = {'user': user,
                           'pagetype': 'user replies',
                           'logout_url': logout_url, 'login_url': login_url,
                           'tweets': tweets,
                           'page_size': len(tweets),'next_page': next_page,
                           }
        path = os.path.join(os.path.dirname(__file__), 'templates/replies.html')
        self.response.out.write(template.render(path, template_values))

    def get(self):
        cur_user = users.get_current_user()
        user = models.Members.all().filter('user', cur_user).get()
        self.show_user_replies(user, self.request.get('next_page'))

# login: required
class ActionHandler(webapp.RequestHandler):
    """Handle 'follow', 'unfollow', 'del', 'fav' actions.
    """
    def get_cur_user(self):
        cur_user = users.get_current_user()
        return models.Members.all().filter('user', cur_user).get()

    def follow(self, who):
        # self.Members.following & Counters
        # who.Members.followers & Counters
        user = self.get_cur_user()
        foed = models.Members.get_by_key_name(who.lower())
        if not foed.username.lower() in user.following:
            user.following.append(foed.username.lower())
            user.put()
            user_counter = models.Counters.get_by_key_name(
                user.username.lower()+'counters', parent=user)
            user_counter.following_counter += 1
            user_counter.put()
        if not user.username.lower() in foed.followers:
            foed.followers.append(user.username.lower())
            foed.put()
            foed_counter = models.Counters.get_by_key_name(
                foed.username.lower()+'counters', parent=foed)
            foed_counter.followers_counter += 1
            foed_counter.put()
        # Push who's tweets into my TimelineQueue
        q = models.Tweets.all().ancestor(foed.key()).order('-when')
        # insert 100 tweets to my timeline queue, no more
        tweets = q.fetch(100)
        for t in tweets:
            # maybe foed was foed before...
            models.TimelineQueue(parent=user,
                                 tweet= t.key(),
                                 bywho= t.bywho,
                                 when= t.when,
                                 ).put()
        # End of follow action

    def unfollow(self, who):
        user = self.get_cur_user()
        unfoed = models.Members.get_by_key_name(who.lower())
        if unfoed.username.lower() in user.following:
            user.following.remove(unfoed.username.lower())
            user.put()
            user_counter = models.Counters.get_by_key_name(
                user.username.lower()+'counters', parent=user)
            user_counter.following_counter -= 1
            user_counter.put()
        if user.username.lower() in unfoed.followers:
            unfoed.followers.remove(user.username.lower())
            unfoed.put()
            unfoed_counter = models.Counters.get_by_key_name(
                unfoed.username.lower()+'counters', parent=unfoed)
            unfoed_counter.followers_counter -= 1
            unfoed_counter.put()
        # TimelineQueue
        q = models.TimelineQueue.all().ancestor(user).filter('bywho', unfoed.username)
        res = q.fetch(100)
        cursor = q.cursor()
        while 0 < len(res) <= 100:
            for r in res:
                r.active = False
                r.put()
            q.with_cursor(cursor)
            res = q.fetch(100)
        # End of unfollow action

    def get_tweet_key(self, tweet_id):
        q = db.Query(models.Tweets, keys_only=True)
        q.filter('tid', int(tweet_id))
        return q.get()

    # tweet_id is string
    def delete(self, tweet_id):
        user = self.get_cur_user()
        tweet = models.Tweets.get_by_id(int(tweet_id), parent=user)
        # is the owner
        if tweet:
            # Tweets & Counters in a transaction
            def txn1(user, tweet):
                tweet.delete()
                counter = models.Counters.get_by_key_name(
                    key_names=user.username.lower()+'counters', parent=user)
                counter.tweets_counter -= 1
                counter.put()
            db.run_in_transaction(txn1, user, tweet)
            # TimelineQueue & Replies (Favorites needed rewrite)
            q1 = models.TimelineQueue.all().filter('tweet', tweet.key())
            res1 = q1.fetch(11)
            cursor1 = q1.cursor()
            while 0 < len(res1) <= 11:
                for t in res1:
                    t.active = False
                    t.put()
                q1.with_cursor(cursor1)
                res1 = q1.fetch(11)
            #
            q2 = models.Replies.all().filter('tweet', tweet.key())
            res2 = q2.fetch(11)
            cursor2 = q2.cursor()
            while 0 < len(res2) <= 11:
                for t in res2:
                    t.delete()
                q2.with_cursor(cursor2)
                res2 = q2.fetch(11)
        else:
            self.error(400)

    def faved_or_not(self, user, tweet_key):
        """Return a Favorites entity"""
        q = models.Favorites.all().ancestor(user.key()).filter('tweet', tweet_key)
        return q.get()

    def favor(self, tweet_id):
        tweet_key = self.get_tweet_key(tweet_id)
        if tweet_key:
            # if faved or not
            user = self.get_cur_user()
            if self.faved_or_not(user, tweet_key):
                self.response.out.write("You have faved this tweet!")
            else:
                # Favorites & Counters
                def txn(user, tweet_key):
                    models.Favorites(parent=user.key(), tweet=tweet_key).put()
                    counter = models.Counters.get_by_key_name(
                        key_names=user.username.lower()+'counters', parent=user)
                    counter.favorites_counter += 1
                    counter.put()
                db.run_in_transaction(txn, user, tweet_key)
        else:
            self.error(400)

    def unfavor(self, tweet_id):
        tweet_key = self.get_tweet_key(tweet_id)
        user = self.get_cur_user()
        if tweet_key:
            faved = self.faved_or_not(user, tweet_key).key()
            if faved:
                def txn(faved, user):
                    db.get(faved).delete()
                    counter = models.Counters.get_by_key_name(
                        key_names=user.username.lower()+'counters', parent=user)
                    counter.favorites_counter -= 1
                    counter.put()
                db.run_in_transaction(txn, faved, user)
            self.response.out.write("You have not faved this tweet.")
        else:
            self.error(400)

    def get(self, action, target):
        do = {'follow': self.follow, 'unfollow': self.unfollow,
              'del': self.delete, 'fav': self.favor, 'unfav': self.unfavor,}
        do[action](target)
