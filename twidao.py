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
            tweets = db.get(map(lambda x: x.tweet.key(), res))
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
            template_values = {'user': 'setting',
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
    def get(self, user, size='normal'):
        if size not in ('origin', 'bigger', 'normal'):
            self.redirect('/notfound')
        avatar = models.Avatars.get_by_key_name(user+size)
        if avatar:
            self.response.headers['Content-Type'] = 'image'
            self.response.out.write(avatar.content)
        # registered but not upload avatar yet
        elif models.Members.get_by_key_name(user):
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
