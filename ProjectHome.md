pydelicious allows you to access the web service of del.icio.us via it's API using Python.

```

  >>> from pydelicious import DeliciousAPI
  >>> from getpass import getpass
  >>> a = DeliciousAPI('username', getpass('Password:'))
  Password:
  >>> # Either succeeds or raises DeliciousError or subclass:
  >>> a.posts_add("http://my.url/", "title", 
  ... extended="description", tags="my tags")
  >>> len(a.posts_all()['posts'])
  1
  >>> a.tags_get() # or: a.request('tags/get')
  {'tags': [{'count': '1', 'tag': 'my'}, {'count': '1', 'tag': 'tags'}]}
  >>> a.posts_update()
  {'update': {'time': (2008, 11, 28, 2, 35, 51, 4, 333, -1)}}
  >>> # Either succeeds or raises DeliciousError or subclass:
  >>> a.posts_delete("http://my.com/")
  >>> len(a.posts_all()['posts'])
  0

```

`pydelicious` is in the Python Package index (PyPi), to install:
```
   easy_install pydelicious
```

The latest code is in the Google SVN repository.
To install from download or source use make or setuptools:
```

  $ make install
  # or 
  $ python setup.py install

```

To get started editing your collection use the included program:

```

  $ dlcs -u <delicious-login>

```

Note the `-C` flag to prevent re-caching in case of large collections.




**IMPORTANT**: pydelicious has not been updated to use the OAuth protocol. New users with a Yahoo account/email will not be able to use this library.