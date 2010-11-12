#!/usr/bin/env python
# encoding: utf-8
"""
delicious_mates.py
http://www.aiplayground.org/artikel/delicious-mates/
"""
import sys, math, re, time, base64, urllib2
from urlparse import urlparse
from getpass import getpass

MAX_MATES = 50
MAX_BOOKMARKS = 1000
BOOKMARK_FILTER = {"shared" : [None, "yes", "no"]}
MATE_MIN_BOOKMARKS = 20
MATE_MIN_COMMON = 2

BOOKMARK_LIST_URL = "https://api.del.icio.us/v1/posts/all"
USER_URL = "http://del.icio.us/"
USER_AGENT_WEB = 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.8.1.9) Gecko/20071105 Firefox/2.0.0.9'
USER_AGENT_API = 'del.icio.us mates +http://www.aiplayground.org/artikel/delicious-mates/'

def ximport(module_name, url):
    """
    Try to import a module; if import fails, download code from
    module url and execute it. This is insecure.
    """
    try:
        mod = __import__(module_name)
    except ImportError:
        modcode = get_page(url)
        open(module_name + ".py", "w").write(modcode)
        mod = __import__(module_name)
    return mod

def get_page(url):
    """
    Returns content of page at url as string.
    """
    request = urllib2.Request(url)
    request.add_header('User-Agent', USER_AGENT_WEB)
    try:
        handle = urllib2.urlopen(request)
    except IOError, e:
        print e
        sys.exit()
    return handle.read()

BeautifulSoup = ximport("BeautifulSoup", "http://www.crummy.com/software/BeautifulSoup/download/BeautifulSoup.py")
deliciousapi = ximport("deliciousapi", "http://code.michael-noll.com/?p=general;a=blob_plain;f=python/tools/deliciousapi.py;hb=HEAD")

def get_authenticated_page(url, username, password):
    """
    Returns content of page requiring authentication as string
    From www.voidspace.org.uk/python/articles/authentication.shtml
    """
    req = urllib2.Request(url)
    req.add_header('User-Agent', USER_AGENT_API)
    try:
        handle = urllib2.urlopen(req)
    except IOError, e:
        pass
    else:
        raise
    try:
        authline = e.headers['www-authenticate']
    except KeyError:
        print e
        sys.exit()
    authobj = re.compile(r'''(?:\s*www-authenticate\s*:)?\s*(\w*)\s+realm=['"]([^'"]+)['"]''', re.IGNORECASE)
    matchobj = authobj.match(authline)
    scheme = matchobj.group(1)
    realm = matchobj.group(2)
    if scheme.lower() != 'basic':
        print 'This only works with BASIC authentication.'
        sys.exit(1)
    base64string = base64.encodestring('%s:%s' % (username, password))[:-1]
    authheader =  "Basic %s" % base64string
    req.add_header("Authorization", authheader)
    try:
        handle = urllib2.urlopen(req)
    except IOError, e:
        print "It looks like the username or password is wrong."
        sys.exit(1)
    thepage = handle.read()
    return thepage

def value_sorted(dic):
    """
    Return dic.items(), sorted by the values stored in the dictionary.
    """
    l = [(num, key) for (key, num) in dic.items()]
    l.sort(reverse=True)
    l = [(key, num) for (num, key) in l]
    return l

def get_account_bookmarks(account_username, account_password):
    """
    Return list of all del.icio.us bookmarks for one user/password
    """
    bookmark_page = get_authenticated_page(BOOKMARK_LIST_URL, account_username, account_password)
    bookmark_soup = BeautifulSoup.BeautifulStoneSoup(bookmark_page)
    bookmarks = [str(post["href"]) for post in bookmark_soup.findAll("post", **BOOKMARK_FILTER)]
    return bookmarks

def get_users_for_bookmark(url):
    """
    Return list of all usernames of del.icio.us users who bookmarked one url
    """
    d = deliciousapi.DeliciousAPI()
    url_metadata = d.get_url(url)
    usernames = [str(n[0]) for n in url_metadata.bookmarks]
    return usernames

def main():
    delicious_users = {}
    account_username = unicode(raw_input("Your del.icio.us username? "))
    account_password = unicode(getpass("Your del.icio.us password? "))
    bookmarks = get_account_bookmarks(account_username, account_password)[:MAX_BOOKMARKS]
    print "\nFetching list of bookmarks ... (%i)" % len(bookmarks)
    
    print "\nFetching list of users for each bookmark ..."
    for i, bookmark in enumerate(bookmarks):
        usernames = get_users_for_bookmark(bookmark)
        print "    %i. %s (%i)" % (i+1, bookmark, len(usernames))
        for username in usernames:
            if username != account_username:
                delicious_users.setdefault(username, (0.0, 0))
                (weight, num_common) = delicious_users[username]
                new_weight = weight + 1.0/math.log(len(usernames)+1.0)
                delicious_users[username] = (new_weight, num_common + 1)
    
    print "\nFinding %i candidates from list of %i users ..." % (MAX_MATES, len(delicious_users))
    friends = {}
    for (username, (weight, num_common)) in value_sorted(delicious_users):
        if num_common >= MATE_MIN_COMMON:
            user_page = get_page(USER_URL + username)
            num_bookmarks = float(re.findall("items\s+\((\d+)\)", user_page)[0])
            print "    %s (%i/%i)" % (username, num_common, num_bookmarks),
            if num_bookmarks >= MATE_MIN_BOOKMARKS:
                print "ok"
                friends[username] = (weight*(num_common/num_bookmarks), num_common, num_bookmarks)
                if len(friends) >= MAX_MATES:
                    break
            else:
                print
            time.sleep(1)
    
    print "\nTop %i del.icio.us mates:" % MAX_MATES
    print "username".ljust(20), "weight".ljust(20), "# common bookmarks".ljust(20), "# total bookmarks".ljust(20), "% common"
    print "--------------------------------------------------------------------------------------------"
    for (username, (weight, num_common, num_total)) in value_sorted(friends)[:MAX_MATES]:
        print username.ljust(20),
        print ("%.5f" % (weight*100)).ljust(20),
        print str(num_common).ljust(20),
        print str(int(num_total)).ljust(20),
        print "%.5f" % ((num_common/num_total)*100.0)


if __name__ == "__main__":
    main()