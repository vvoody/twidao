from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import models

class MainPage(webapp.RequestHandler):
    def get(self):
        self.response.out.write("Hello world!")

# login: required
class SignupPage(webapp.RequestHandler):
    def get(self):
        cur_user = users.get_current_user()
        q = db.GqlQuery("SELECT * FROM Members WHERE user = :1", cur_user)
        user = q.get()
        if user:  # registered
            self.redirect('/')
        logout_url = users.create_logout_url('/')
        template_values = {'logout_url': logout_url,
                           'username': 'foobar'}
        path = os.path.join(os.path.dirname(__file__), 'templates/signup.html')
        self.response.out.write(template.render(path, template_values))
    def post(self):
        pass

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/signup', SignupPage)], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
