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

application = webapp.WSGIApplication([('/task/avatar/resize', ResizeAvatar),
                                      ], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
