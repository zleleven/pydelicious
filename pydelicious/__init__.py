"""Library to access del.icio.us data via Python.

An introduction to the code is given in the project's README.
Access to the v1 API is provided by DeliciousAPI. Work on the v2 API (with
OAuth) and the feed APIs is a work in progress.

pydelicious is released under the BSD license. See license.txt for details
and the copyright holders.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

TODO:
 - do something interesting with feeds?
 - pick some docformat, stick with it (this is not all rSt)
 - distribute license, readme docs via setup.py?
 - automatic release build?
"""
import sys
import os
import time
import datetime
import locale
import logging
import httplib
import urllib2
from urllib import urlencode, quote_plus
from StringIO import StringIO
from pprint import pformat

try:
    # Python >= 2.5
    from hashlib import md5
except ImportError:
    from md5 import md5

try:
    # Python >= 2.5
    from elementtree.ElementTree import parse
    logging.debug("Using ``elementtree.ElementTree``. ")
except ImportError:
    from xml.etree.ElementTree import parse
    logging.debug("Using ``xml.etree.ElementTree``. ")

try:
    import feedparser
except ImportError:
    logging.warning("Feedparser not available, no RSS parsing.")
    feedparser = None


### Static config

__rcs_id__ = "$Id$"[3:-1]
__version__ = '0.7'
__author__ = 'Frank Timmermann <regenkind_at_gmx_dot_de>'
    # GP: does not respond to emails
__contributors__ = [
    'Greg Pinero',
    'Berend van Berkum <berend+pydelicious@dotmpe.com>']
__url__ = 'http://code.google.com/p/pydelicious/'
# Old URL: 'http://deliciouspython.python-hosting.com/'
__author_email__ = ""
#__docformat__ = "restructuredtext en"
__description__ = "pydelicious.py allows access the web service of " \
    "del.icio.us via it's API through Python."
__long_description__ = "The goal is to design an easy to use and fully " \
    "functional Python interface to del.icio.us."


### Logging

DEBUG_NET = 2
DEBUG_COMM = 3
DEBUG_PARSE = 7
INFO_API = 12

log = logging.getLogger('pydelicious')
logging.addLevelName(DEBUG_COMM, 'COMM')
logging.addLevelName(DEBUG_PARSE, 'PARSE')
logging.addLevelName(INFO_API, 'API')

VERBOSITY = 0
"Logging output level. "

def set_verbosity(level):
    VERBOSITY = level
    assert 50 >= verbosity >= 0, "pydelicious logging output must be between 0 (NOTSET) and 50 (CRITICAL)"
    log.setLevel(level)


if 'DLCS_DEBUG' in os.environ:
    # Set logger output level from environment
    verbosity = int(os.environ['DLCS_DEBUG'])
    set_verbosity(verbosity)
    log.debug("Logging output level to %i by DLCS_DEBUG env.", verbosity)


### Constants specific to delicious.com

DLCS_WAIT_TIME = 4
"Time to wait between API requests"
DLCS_REQUEST_TIMEOUT = 444
"Seconds before socket triggers timeout"
DLCS_API_REALM = 'del.icio.us API'
DLCS_API_HOST = 'api.del.icio.us'
DLCS_API_PATH = 'v1'
DLCS_API = "https://%s/%s" % (DLCS_API_HOST, DLCS_API_PATH)
DLCS_RSS = 'http://del.icio.us/rss/'
DLCS_FEEDS = 'http://feeds.delicious.com/v2/'
DLCS_OK_MESSAGES = ('done', 'ok')
"Known text values of positive del.icio.us <result/> answers"
DLCS_LIST_RESOURCES = ('tags', 'posts', 'dates', 'bundles')
DLCS_TIME_ATTR = ('time', 'dt', 'update')


### Misc. frontend vars and constants

PREFERRED_ENCODING = locale.getpreferredencoding()
# XXX: might need to check sys.platform/encoding combinations here, ie
#if sys.platform == 'darwin' || PREFERRED_ENCODING == 'macroman:
#   PREFERRED_ENCODING = 'utf-8'
if not PREFERRED_ENCODING:
    PREFERRED_ENCODING = 'iso-8859-1'

ISO_8601_DATETIME = '%Y-%m-%dT%H:%M:%SZ'

USER_AGENT = 'pydelicious/%s %s' % (__version__, __url__)



HTTP_PROXY = None
if 'HTTP_PROXY' in os.environ:
    HTTP_PROXY = os.environ['HTTP_PROXY']
    log.debug( "Set HTTP_PROXY to %i from env.", HTTP_PROXY )

try:
    # Timeout socket was a fix for pre-2.3 Python socket behaviour
    import timeoutsocket as socket
    # Old URL: http://www.timo-tasi.org/python/timeoutsocket.py
except ImportError:
    import socket

def set_timeout(value):
    if hasattr(socket, 'setdefaulttimeout'):
        socket.setdefaulttimeout(value)
    elif hasattr(socket, 'setDefaultSocketTimeout'):        
        timeoutsocket.setDefaultSocketTimeout(value)
    else:
        log.warning("Unable to set timeout. ")

log.debug( "Set socket timeout to %s seconds", DLCS_REQUEST_TIMEOUT )
set_timeout(DLCS_REQUEST_TIMEOUT)


### Utility classes

class _Waiter:
    """Waiter makes sure a certain amount of time passes between
    successive calls of `Waiter()`.

    Some attributes:
      :wait: the minimum time needed between calls
      :last: time of last call
      :waited: the number of calls throttled

    pydelicious.Waiter is an instance created when the module is loaded.
    """
    def __init__(self, wait):
        self.wait = wait
        self.last = 0;
        self.waited = 0

    def __call__(self):
        tt = time.time()
        wait = self.wait

        timeago = tt - self.last

        if timeago < wait:
            wait = wait - timeago
            log.info("Waiting %s seconds.", wait)
            time.sleep(wait)
            self.waited += 1
            self.last_call = tt + wait
        else:
            self.last_call = tt

Waiter = _Waiter(DLCS_WAIT_TIME)


class PyDeliciousException(Exception):
    " Standard pydelicious error. "

class PyDeliciousThrottled(Exception):
    " The server is unwilling to service request. "

class PyDeliciousUnauthorized(Exception): pass

class DeliciousError(Exception):
    " The server reported an error upon API request. "

    @staticmethod
    def for_message(error_string, path, **params):
        " Raise for known backend response. "
        if error_string == 'item already exists':
            return DeliciousItemExistsError(params['url'])
        else:
            return DeliciousError("%s, while calling <%s?%s>" % (error_string,
                    path, urlencode(params)))

class DeliciousItemExistsError(DeliciousError):
    " Raised then adding an already existing post. "


class DeliciousHTTPErrorHandler(urllib2.HTTPDefaultErrorHandler):
    " An ``urllib2`` handler for 401 and 503 responses. "

    def http_error_401(self, req, fp, code, msg, headers):
        raise PyDeliciousUnauthorized, "Check credentials."

    def http_error_999(self, req, fp, code, msg, headers):
        return self.http_error_503(req, fp, code, msg, headers)

    def http_error_503(self, req, fp, code, msg, headers):
        errmsg = "Try again later."
        if 'Retry-After' in headers:
            errmsg = "You may try again after %s" % headers['Retry-After']
        raise PyDeliciousThrottled, errmsg


### Data instance wrapper classes

class DeliciousAPIResource:
    def __init__(self, api, **props):
        self.api = api
        self.data = props

    def __getitem__(self, key):
        print self.api
        print self.data
        return self.data[key]

    def __str__(self):
        return "%s;%s:%s" % (self.__class__.__name__, 
                ';'.join(["%s=%s" %(k, self.data[k]) for k in self.data]),
                self.api )

    def _date(self, dt):
        dst = dt[-1] # TODO: tz
        #logging.warning("todo: tz %s" % dt)
        return datetime.datetime(*dt[0:6])

    def from_response_data(clss, api, kind, data):
        if kind == 'result':
            if not data in DLCS_OK_MESSAGES:
                # Raise error
                raise DeliciousError.for_message(msg or 'Unknown error',
                        path, **params)
            return clss( api, *data )

        elif kind == 'update':
            getter = lambda self: self._date( self.data['time'] )
            setattr( clss, 'time', property( getter ))
            return clss( api, **data )

        elif kind in DLCS_LIST_RESOURCES:
            list_props, list_data = data
            for p in list_props:
                if p in DLCS_TIME_ATTR:
                    getter = lambda self: self._date(self.data[p])
                else:    
                    getter = lambda self: self.data[p]
                setattr( clss, p, property( getter ))
            setattr( clss, kind, lambda self: self.list_data )
            return clss( api, list_data, **list_props )

    from_response_data = classmethod(from_response_data)

class DeliciousDone(DeliciousAPIResource):
    def __init__(self, api, message, **props):
        DeliciousAPIResource.__init__(self, api, **props)
        self.message = message

class DeliciousUpdate(DeliciousAPIResource): 
    def __str__(self):
        return "Last update for %s: %s" % (self.api, self.isoformat())

    def isoformat(self):
        return self.time.strftime(ISO_8601_DATETIME)

class DeliciousListResource(DeliciousAPIResource):
    def __init__(self, api, list_data, **list_props):
        DeliciousAPIResource.__init__(self, api, **list_props)
        self.list_data = list_data

    def __len__(self):
        return len(self.list_data)

    def __iter__(self):
        return iter(self.list_data)

    def __str__(self):
        return "%s, %i items;%s:%s" % (self.__class__.__name__, len(self), 
                ';'.join(["%s=%s" %(k, self.data[k]) for k in self.data]),
                self.api )

class DeliciousPostsList(DeliciousListResource): pass

    #    def __str__(self):
    #        list_str = DeliciousListResource.__str__(self)
    #        return list_str + ", last updated %s" % self.date.isoformat()

class DeliciousRecentPosts(DeliciousPostsList): pass
class DeliciousChangeManifest(DeliciousPostsList): pass
class DeliciousTagsList(DeliciousListResource): pass
class DeliciousDatesList(DeliciousListResource): pass
class DeliciousUser(DeliciousAPIResource): pass 
class DeliciousPost(DeliciousAPIResource): pass

#    def href(self, url):
#        """Return the del.icio.us url at which the HTML page with posts for
#        ``url`` can be found.
#        """
#        return "http://del.icio.us/url/?url=%s" % (url,)




### Utility functions

def dict0(d):
    "Removes empty string values from dictionary"
    return dict([(k,v) for k,v in d.items()
            if v=='' and isinstance(v, basestring)])


def http_request(url, user_agent=USER_AGENT, retry=4, opener=None):
    """
    Retrieve the contents referenced by the URL using urllib2.

    Retries up to four times (default) on exceptions.
    """
    request = urllib2.Request(url, headers={'User-Agent':user_agent})

    if not opener:
        opener = urllib2.build_opener()

    # Remember last error
    e = None

    tries = retry;
    while tries:
        try:
            return opener.open(request)

        except urllib2.HTTPError, e:
            # reraise unexpected protocol errors as PyDeliciousException
            raise PyDeliciousException, (str(e), url)

        except urllib2.URLError, e:
            # Repeat request on time-out errors
            # xxx: Ugly check for time-out errors
            #if len(e)>0 and 'timed out' in arg[0]:
            logging.warning("HTTP request failed: '%s', %s tries left.", e, tries)
            Waiter()
            tries = tries - 1

    raise PyDeliciousException, \
            "Unable to retrieve data at '%s', %s" % (url, e)


### Delicious.com API utilities

def build_api_opener(host, user, passwd, extra_handlers=()):
    """
    Build a urllib2 style opener from several handlers:

    - HTTP Basic authorization with user-info for one host.
    - Delicious specific HTTP error handling.
    - A proxy handler if HTTP_PROXY env-var is set.
    """

    password_manager = urllib2.HTTPPasswordMgr()
    password_manager.add_password(DLCS_API_REALM, host, user, passwd)
    auth_handler = urllib2.HTTPBasicAuthHandler(password_manager)

    handlers = ( auth_handler, DeliciousHTTPErrorHandler(), ) + extra_handlers

    if VERBOSITY >= DEBUG_NET:
        # httplib prints extra info on non-zero debuglevel 
        httpdebug = urllib2.HTTPHandler(debuglevel=1)
        handlers += ( httpdebug, )

    if HTTP_PROXY:
        handlers += ( urllib2.ProxyHandler( {'http': HTTP_PROXY} ), )

    o = urllib2.build_opener(*handlers)

    return o


def dlcs_api_opener(user, passwd):
    "Build an opener for DLCS_API_HOST, see build_api_opener(). "

    return build_api_opener(DLCS_API_HOST, user, passwd)


#def dlcs_api_request(path, params='', user='', passwd='', throttle=True,
#        opener=None):
#    """
#    Retrieve/query a path within the del.icio.us API.
#
#    This implements a minimum interval between calls to avoid
#    throttling. [#]_ Use param 'throttle' to turn this behaviour off.
#
#    .. [#] http://del.icio.us/help/api/
#    """
#    if throttle:
#        Waiter()
#
#    if params:
#        url = "%s/%s?%s" % (DLCS_API, path, urlencode(params))
#    else:
#        url = "%s/%s" % (DLCS_API, path)
#
#    log.log(DEBUG_COMM, "dlcs_api_request: %s", url)
#
#    if not opener:
#        opener = dlcs_api_opener(user, passwd)
#
#    fl = http_request(url, opener=opener)
#
#    log.log(DEBUG_COMM, "dlcs_api_request response headers:\n%s", 
#            pformat(fl.info().headers))
#
#    return fl


def dlcs_encode_params(params, usercodec=PREFERRED_ENCODING):
    """Turn all param values (int, list, bool) into utf8 encoded strings.
    """

    if params:
        for key in params.keys():
            if isinstance(params[key], bool):
                if params[key]:
                    params[key] = 'yes'
                else:
                    params[key] = 'no'

            elif isinstance(params[key], int):
                params[key] = str(params[key])

            elif not params[key]:
                # strip/ignore empties other than False or 0
                del params[key]
                continue

            elif isinstance(params[key], list):
                params[key] = " ".join(params[key])

            elif not isinstance(params[key], unicode):
                params[key] = params[key].decode(usercodec)

            assert isinstance(params[key], basestring)

        params = dict([ (k, v.encode('utf8'))
                for k, v in params.items() if v])

    return params

def dlcs_parse_xml(data, split_tags=False, success_msgs=DLCS_OK_MESSAGES):
    " Parse delicious XML to dicts 'n lists.  "

    if not hasattr(data, 'read'):
        data = StringIO(data)
    #log.log(DEBUG_PARSE, "dlcs_parse_xml: parsing %s bytes.", len(data.read()))

    doc = parse(data)
    root = doc.getroot()
    fmt = root.tag

    log.log(DEBUG_PARSE, "dlcs_parse_xml: found '%s' document. ", fmt)

    scandate = lambda dt: time.strptime(dt, ISO_8601_DATETIME)

    # Split up into three cases: Data (list), Result or Update
    if fmt in DLCS_LIST_RESOURCES:
        # Data: expect a list of data elements, dicts with properties.
        # Use `fmt` (without last 's') to find data elements.
        # Theres no contents, attributes contain all the data we need;
        list_data = [el.attrib for el in doc.findall(fmt[:-1])]
        for item in list_data:
            for k in DLCS_TIME_ATTR:
                if k in item:
                    item[k] = scandate(item[k])
                elif k == 'tags':
                    item[k] = [t.strip() for t in e[k].strip().split(' ')]
        # Root element might have attributes too, append dict.
        list_props = root.attrib
        for tk in DLCS_TIME_ATTR:
            if tk in list_props:
                list_props[tk] = scandate(list_props[tk])
        return fmt, (list_props, list_data)

    elif fmt == 'result':
        # Result: answer to operations
        if root.attrib.has_key('code'):
            msg = root.attrib['code']
        else:
            msg = root.text
        return fmt, msg            

    elif fmt == 'update':
        return fmt, { 'time': scandate(root.attrib['time']) }

    else:
        raise PyDeliciousException, "Unknown XML document format '%s'" % fmt


### Delicious.com feeds

# TODO: wrap this in nice DeliciousFeeds

def dlcs_rss_request(tag="", popular=0, user="", url=''):
    """Parse a RSS request.

    This requests old (now undocumented?) URL paths that still seem to work.
    """

    tag = quote_plus(tag)
    user = quote_plus(user)

    if url != '':
        # http://del.icio.us/rss/url/efbfb246d886393d48065551434dab54
        url = DLCS_RSS + 'url/%s' % md5(url).hexdigest()

    elif user != '' and tag != '':
        url = DLCS_RSS + '%(user)s/%(tag)s' % {'user':user, 'tag':tag}

    elif user != '' and tag == '':
        # http://del.icio.us/rss/delpy
        url = DLCS_RSS + '%s' % user

    elif popular == 0 and tag == '':
        url = DLCS_RSS

    elif popular == 0 and tag != '':
        # http://del.icio.us/rss/tag/apple
        # http://del.icio.us/rss/tag/web2.0
        url = DLCS_RSS + "tag/%s" % tag

    elif popular == 1 and tag == '':
        url = DLCS_RSS + 'popular/'

    elif popular == 1 and tag != '':
        url = DLCS_RSS + 'popular/%s' % tag

    rss = http_request(url).read()

    # assert feedparser, "dlcs_rss_request requires feedparser to be installed."
    if not feedparser:
        return rss

    rss = feedparser.parse(rss)

    posts = []
    for e in rss.entries:
        if e.has_key("links") and e["links"]!=[] and e["links"][0].has_key("href"):
            url = e["links"][0]["href"]
        elif e.has_key("link"):
            url = e["link"]
        elif e.has_key("id"):
            url = e["id"]
        else:
            url = ""
        if e.has_key("title"):
            description = e['title']
        elif e.has_key("title_detail") and e["title_detail"].has_key("title"):
            description = e["title_detail"]['value']
        else:
            description = ''
        try: tags = e['categories'][0][1]
        except:
            try: tags = e["category"]
            except: tags = ""
        if e.has_key("modified"):
            dt = e['modified']
        else:
            dt = ""
        if e.has_key("summary"):
            extended = e['summary']
        elif e.has_key("summary_detail"):
            e['summary_detail']["value"]
        else:
            extended = ""
        if e.has_key("author"):
            user = e['author']
        else:
            user = ""
        #  time = dt ist weist auf ein problem hin
        # die benennung der variablen ist nicht einheitlich
        #  api senden und
        #  xml bekommen sind zwei verschiedene schuhe :(
        posts.append({'url':url, 'description':description, 'tags':tags,
                'dt':dt, 'extended':extended, 'user':user})
    return posts

delicious_v2_feeds = {
    #"Bookmarks from the hotlist"
    '': "%(format)s",
    #"Recent bookmarks"
    'recent': "%(format)s/recent",
    #"Recent bookmarks by tag"
    'tagged': "%(format)s/tag/%(tags)s",
    #"Popular bookmarks"
    'popular': "%(format)s/popular",
    #"Popular bookmarks by tag"
    'popular_tagged': "%(format)s/popular/%(tag)s",
    #"Recent site alerts (as seen in the top-of-page alert bar on the site)"
    'alerts': "%(format)s/alerts",
    #"Bookmarks for a specific user"
    'user': "%(format)s/%(username)s",
    #"Bookmarks for a specific user by tag(s)"
    'user_tagged': "%(format)s/%(username)s/%(tags)s",
    #"Public summary information about a user (as seen in the network badge)"
    'user_info': "%(format)s/userinfo/%(username)s",
    #"A list of all public tags for a user"
    'user_tags': "%(format)s/tags/%(username)s",
    #"Bookmarks from a user's subscriptions"
    'user_subscription': "%(format)s/subscriptions/%(username)s",
    #"Private feed for a user's inbox bookmarks from others"
    'user_inbox': "%(format)s/inbox/%(username)s?private=%(key)s",
    #"Bookmarks from members of a user's network"
    'user_network': "%(format)s/network/%(username)s",
    #"Bookmarks from members of a user's network by tag"
    'user_network_tagged': "%(format)s/network/%(username)s/%(tags)s",
    #"A list of a user's network members"
    'user_network_member': "%(format)s/networkmembers/%(username)s",
    #"A list of a user's network fans"
    'user_network_fan': "%(format)s/networkfans/%(username)s",
    #"Recent bookmarks for a URL"
    'url': "%(format)s/url/%(urlmd5)s",
    #"Summary information about a URL (as seen in the tagometer)"
    'urlinfo': "json/urlinfo/%(urlmd5)s",
}

def dlcs_feed(name_or_url, url_map=delicious_v2_feeds, count=15, **params):

    """
    Request and parse a feed. See delicious_v2_feeds for available names and
    required parameters. Format defaults to json.
    """

# http://delicious.com/help/feeds
# TODO: plain or fancy

    format = params.setdefault('format', 'json')
    if count == 'all':
# TODO: fetch all
        count = 100

    if name_or_url in url_map:
        params['count'] = count
        url = DLCS_FEEDS + url_map[name_or_url] % params

    else:
        url = name_or_url

    feed = http_request(url).read()

    if format == 'rss':
        if feedparser:
            rss = feedparser.parse(feed)
            return rss

        else:
            return feed

    elif format == 'json':
        return feed


### Main module class

class DeliciousAPI:

    """
    A single-user Python facade to the del.icio.us HTTP API.

    See http://delicious.com/help/api.
    """

    fetch_raw = '_raw'
    " Parameter name to retrieve raw response data and bypass any parsing. "

    def __init__(self, user, passwd, 
            codec=PREFERRED_ENCODING,
            api_path=DLCS_API,
            throttle=Waiter,
            parse_response=dlcs_parse_xml,
            build_opener=dlcs_api_opener, 
            encode_params=dlcs_encode_params,):

        """
        Initialize access to the API for `user` with `passwd`, along with the
        following other settings.

        - `codec` sets the encoding of the arguments, which defaults to the
          users preferred locale.

        - `wrapdata` indicates wether to wrap and unwrap the the returned data.

        - `build_opener` is a callable factory for an urllib2 opener. The opener 
           is rebuild upon user-switch (see `reload()`).

        - `encode_params` is a callable used before every API request to do
          sanitizing on the options before sending them to the urllib opener.

        - `parse_response` is a callable to parse the raw response stream, 
          which is then inspected to detect the kind of the response and
          e.g. raise and error.  

        See the following module functions for implementation:

        - dlcs_api_opener
        - dlcs_encode_params
        - dlcs_parse_xml
        """

        assert user != ""

        self.api_path = api_path
        self.codec = codec
        self.throttle = throttle

        assert callable(encode_params)
        self.encode_params = encode_params
        assert callable(parse_response)
        self.parse_response = parse_response
        self.reload(user, passwd, build_opener=build_opener)
        
    def reload(self, user, passwd, build_opener=dlcs_api_opener):
        """
        Reset the API for another user.
        """
        self.user = user
        self.passwd = passwd
        self.opener = build_opener(user, passwd)

    ### Core functionality

    def request(self, path, **params):
        """
        Opens API URL with parameters, returns raw stream.
        """
        if self.throttle:
            self.throttle()

        # XXX: Encode params should change into something with real validation
        params = self.encode_params(params)
        if params:
            requrl = "%s/%s?%s" % (self.api_path, path, urlencode(params))
        else:
            requrl = "%s/%s" % (self.api_path, path)

        log.log(DEBUG_COMM, "DeliciousAPI request: %s", requrl)

        fl = http_request(requrl, opener=self.opener)

        log.log(DEBUG_COMM, "DeliciousAPI request response headers:\n%s", 
                pformat(fl.info().headers))

        return fl

    def api_handler(api_path, return_type, docstr=''):
        """
        API-call method factory. This is a sort of 'decorator' for `request`,
        except that this uses an signature incompatible with Python decorators
        and the definitions use a pre-2.3 compatible syntax.

        Returns the callable API method. Parameters are not validated or
        restricted in any, except by the presence of `fetch_raw` (which is not
        sent to the server).
        """
        def api_request(self, **params):
            fl = self.request(api_path, **params)

            if self.fetch_raw in params:
                logging.debug("Returning raw response by '%s' parameter.",
                        self.fetch_raw)
                return fl

            else:
                kind, data = self.parse_response(fl.read())
                return return_type.from_response_data(self, kind, data)

        api_request.__doc__ = docstr
        return api_request
#    api_handler = classmethod(api_handler)

    def __repr__(self):
        return "DeliciousAPI(%s)" % self.user

    def __src__(self):
        return "Delicious %s API (%s)" % (DLCS_API_PATH, self.user)


    ### Delicious Tags

    tags_get = api_handler('tags/get', DeliciousTagsList,
        """Returns a list of tags and the number of times it is used by the
        user:: 

            <tags>
                <tag tag="TagName" count="888">

        """)

    tags_delete = api_handler('tags/delete', DeliciousDone,
        """Delete an existing tag.

        &tag=TAG
            (required) Tag to delete
        """)

    tags_rename = api_handler('tags/rename', DeliciousDone,
        """Rename an existing tag with a new tag name.

        &old=TAG
            (required) Tag to rename.
        &new=TAG
            (required) New tag name.
        """)


    ### Delicious Posts

    posts_update = api_handler('posts/update', DeliciousUpdate,
        """Returns the last update time for the user. Use this before calling
        `posts_all` to see if the data has changed since the last fetch.
        ::

            <update time="CCYY-MM-DDThh:mm:ssZ">
        """)

    posts_dates = api_handler('posts/dates', DeliciousDatesList,
        """Returns a list of dates with the number of posts at each date.
        ::

            <dates>
                <date date="CCYY-MM-DD" count="888">

        &tag={TAG}
            (optional) Filter by this tag
        """)

    posts_get = api_handler('posts/get', DeliciousPostsList,
        """Returns posts matching the arguments. If no date or url is given,
        most recent date will be used.
        ::

            <posts dt="CCYY-MM-DD" tag="..." user="...">
                <post ...>

        &tag={TAG} {TAG} ... {TAG}
            (optional) Filter by this/these tag(s).
        &dt={CCYY-MM-DDThh:mm:ssZ}
            (optional) Filter by this date, defaults to the most recent date on
            which bookmarks were saved.
        &url={URL}
            (optional) Fetch a bookmark for this URL, regardless of date.
        &hashes=MD5[,]
            (optional) Fetch multiple bookmarks by one or more URL MD5s
            regardless of date.
        &meta=yes
            (optional) Include change detection signatures on each item in a
            'meta' attribute. Clients wishing to maintain a synchronized local
            store of bookmarks should retain the value of this attribute - its
            value will change when any significant field of the bookmark
            changes.
        """)

    posts_recent = api_handler('posts/recent', DeliciousRecentPosts,
        """Returns a list of the most recent posts, filtered by argument.
        ::

            <posts tag="..." user="...">
                <post ...>

        &tag={TAG}
            (optional) Filter by this tag.
        &count={1..100}
            (optional) Number of items to retrieve (Default:15, Maximum:100).
        """)

    posts_all = api_handler('posts/all', DeliciousPostsList,
        """Returns all posts. Please use sparingly. Call the `posts_update`
        method to see if you need to fetch this at all.
        ::

            <posts tag="..." user="..." update="CCYY-MM-DDThh:mm:ssZ">
                <post ...>

        &tag
            (optional) Filter by this tag.
        &start={#}
            (optional) Start returning posts this many results into the set.
        &results={#}
            (optional) Return this many results.
        &fromdt={CCYY-MM-DDThh:mm:ssZ}
            (optional) Filter for posts on this date or later
        &todt={CCYY-MM-DDThh:mm:ssZ}
            (optional) Filter for posts on this date or earlier
        &meta=yes
            (optional) Include change detection signatures on each item in a
            'meta' attribute. Clients wishing to maintain a synchronized local
            store of bookmarks should retain the value of this attribute - its
            value will change when any significant field of the bookmark
            changes.
        &hashes
            (optional, exclusive) Do not fetch post details but a posts
            manifest with url- and meta-hashes used to detect changes.
            Other options do not apply.
        """)

    posts_add = api_handler('posts/add', DeliciousDone, 
        """Add a post to del.icio.us. Returns a `result` message or raises an
        ``DeliciousError``. See ``self.request()``.

        &url (required)
            the url of the item.
        &description (required)
            the description of the item.
        &extended (optional)
            notes for the item.
        &tags (optional)
            tags for the item (space delimited).
        &dt (optional)
            datestamp of the item (format "CCYY-MM-DDThh:mm:ssZ").
            Requires a LITERAL "T" and "Z" like in ISO8601 at
            http://www.cl.cam.ac.uk/~mgk25/iso-time.html for example:
            "1984-09-01T14:21:31Z"
        &replace=no (optional) - don't replace post if given url has already
            been posted.
        &shared=yes (optional) - wether the item is public.
        """)

    posts_delete = api_handler('posts/delete', DeliciousDone,
        """Delete a post from del.icio.us. Returns a `result` message or
        raises an ``DeliciousError``. See ``self.request()``.

        &url (required)
            the url of the item.
        """)


    ### Delicious Bundles
    def bundles_all(self, **kwds):
        """Retrieve user bundles from del.icio.us.
        ::

            <bundles>
                <bundel name="..." tags=...">
        """
        return self.request("tags/bundles/all", **kwds)

    def bundles_set(self, bundle, tags, **kwds):
        """Assign a set of tags to a single bundle, wipes away previous
        settings for bundle. Returns a `result` messages or raises an
        ``DeliciousError``. See ``self.request()``.

        &bundle (required)
            the bundle name.
        &tags (required)
            list of tags.
        """
        if type(tags)==list:
            tags = " ".join(tags)
        return self.request("tags/bundles/set", bundle=bundle, tags=tags,
                **kwds)

    def bundles_delete(self, bundle, **kwds):
        """Delete a bundle from del.icio.us. Returns a `result` message or
        raises an ``DeliciousError``. See ``self.request()``.

        &bundle (required)
            the bundle name.
        """
        return self.request("tags/bundles/delete", bundle=bundle, **kwds)



### Convenience functions on this package

def add(user, passwd, url, description, tags="", extended="", dt=None,
        replace=False):
    DeliciousAPI(user, passwd).posts_add(url=url, description=description,
            extended=extended, tags=tags, dt=dt, replace=replace)

def get(user, passwd, tag="", dt=None, count=0, hashes=[]):
    "Returns a list of posts for the user"
    posts = DeliciousAPI(user, passwd).posts_get(
            tag=tag, dt=dt, hashes=hashes)['posts']
    if count: posts = posts[:count]
    return posts

def get_update(user, passwd):
    "Returns the last update time for the user."
    return DeliciousAPI(user, passwd).posts_update()['update']['time']

def get_all(user, passwd, tag="", start=0, results=100, fromdt=None,
        todt=None):
    "Returns a list with all posts. Please use sparingly. See `get_updated`"
    return DeliciousAPI(user, passwd).posts_all(tag=tag, start=start,
            results=results, fromdt=fromdt, todt=todt, meta=True)['posts']

def get_tags(user, passwd):
    "Returns a list with all tags for user."
    return DeliciousAPI(user=user, passwd=passwd).tags_get()['tags']

def delete(user, passwd, url):
    "Delete the URL from the del.icio.us account."
    DeliciousAPI(user, passwd).posts_delete(url=url)

def rename_tag(user, passwd, oldtag, newtag):
    "Rename the tag for the del.icio.us account."
    DeliciousAPI(user=user, passwd=passwd).tags_rename(old=oldtag, new=newtag)


### RSS functions

def getrss(tag="", popular=0, url='', user=""):
    """Get posts from del.icio.us via parsing RSS.

    tag (opt) sort by tag
    popular (opt) look for the popular stuff
    user (opt) get the posts by a user, this striks popular
    url (opt) get the posts by url
    """
    return dlcs_rss_request(tag=tag, popular=popular, user=user, url=url)

def get_userposts(user):
    "parse RSS for user"
    return getrss(user=user)

def get_tagposts(tag):
    "parse RSS for tag"
    return getrss(tag=tag)

def get_urlposts(url):
    "parse RSS for URL"
    return getrss(url=url)

def get_popular(tag=""):
    "parse RSS for popular URLS for tag"
    return getrss(tag=tag, popular=1)


### JSON feeds
# TODO: untested

def json_posts(user, count=15, tag=None, raw=True):
    """
    user
    count=###   the number of posts you want to get (default is 15, maximum 
                is 100)
    raw         a raw JSON object is returned, instead of an object named 
                Delicious.posts
    """
    url = "http://del.icio.us/feeds/json/" + \
            dlcs_encode_params({0:user})[0]
    if tag: url += '/'+dlcs_encode_params({0:tag})[0]

    return dlcs_feed(url, count=count, raw=raw)


def json_tags(user, atleast, count, sort='alpha', raw=True, callback=None):
    """
    user
    atleast=###         include only tags for which there are at least ### 
                        number of posts.
    count=###           include ### tags, counting down from the top.
    sort={alpha|count}  construct the object with tags in alphabetic order 
                        (alpha), or by count of posts (count).
    callback=NAME       wrap the object definition in a function call NAME(...),
                        thus invoking that function when the feed is executed.
    raw                 a pure JSON object is returned, instead of code that 
                        will construct an object named Delicious.tags.
    """
    url = 'http://del.icio.us/feeds/json/tags/' + \
            dlcs_encode_params({0:user})[0]
    return dlcs_feed(url, atleast=atleast, count=count, sort=sort, raw=raw, 
            callback=callback)


def json_network(user, raw=True, callback=None):
    """
    callback=NAME       wrap the object definition in a function call NAME(...)
    ?raw                a raw JSON object is returned, instead of an object named 
                        Delicious.posts
    """
    url = 'http://del.icio.us/feeds/json/network/' + \
            dlcs_encode_params({0:user})[0]
    return dlcs_feed(url, raw=raw, callback=callback)


def json_fans(user, raw=True, callback=None):
    """
    callback=NAME       wrap the object definition in a function call NAME(...)
    ?raw                a pure JSON object is returned, instead of an object named 
                        Delicious.
    """
    url = 'http://del.icio.us/feeds/json/fans/' + \
            dlcs_encode_params({0:user})[0]
    return dlcs_feed(url, raw=raw, callback=callback)


### delicious V2 feeds

def getfeed(name, **params):
    return dlcs_feed(name, **params)

# vim:et:
