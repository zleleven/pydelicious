# Command-Line del.icio.us #

`dlcs` is an executable script that acts as a text-user-interface [TUI](TUI.md) in front
of pydelicious.DeliciousAPI. It offers some facilities to get data from your
online bookmark collection and to perfom operations. See:

```
    % dlcs --help
```

The tool enables quick access but the server communication might be slow and
when doing multiple expensive requests del.icio.us could throttle you and
return 503's. This all depends on your collection size (posts/tags/bundles)
ofcourse.

The post and tag lists are stored locally and these caches must be
updated in one run. For nettiquette's sake, prevent unnecesary refreshes
using the -C flag. In the future, refreshing the cache should get more
fine-grained.

## Quickstart ##
First-time run `dlcs`:

```
    % dlcs -u <username>
```

Then post any URL using:

```
    % dlcs postit <URL>
```

Or use some other often used command like:
```

$ dlcs help rename
rename a tag to one or more tags.

        % dlcs rename oldtag newtag(s)

$ dlcs help findtags
Search all tags for (a part of) a tag.
 
$ dlcs help tagged
Request all posts for a tag or overlap of tags. Print URLs.

        % dlcs tagged tag [tag2 ...]

```

## Configuration ##
Your username and password can be stored in an INI formatted configuration
file under section name 'dlcs'. The default location is ~/.dlcs-rc
but this can be changed using command line options. If no username or
password are provided `dlcs` will use your login name and prompt for the
password. Following the quickstart described above, this file should have been created
automaticly. **Your del.icio.us password is saved there in plain text**, apply whatever r/w control you require.

## Limitation ##
- Bundle sizes are restricted by the maximum URL size [xxx:length?], the del.icio.us web interface allows bigger bundles.

## Integration ##
When using curses based browsers you may have to miss the javascript
bookmarklets since most TUI browsers don't support these. That is why dlcs
has a command `postit` that takes the URL and fires up your favorite editor
to offer the same functionality. E.g.,
`dlcs postit http://code.google.com/p/pydelicious/` should present you a temporary file
with something like:

```
  [http://code.google.com/p/pydelicious/]
  extended =
  hash = fed81a2bedd28f104c39525760fb748e
  description = pydelicious - Google Code
  replace = Yes
  tag = pydelicious python xml api 2006 http:del.icio.us code projects tags web 2007 2008
  meta = 2c6c592bc80d78852d81c1973966b9c1
  time = 2006-10-25T00:39:11Z
  shared = Yes
```

If a URL has already been posted that data is fetched from the server and
included so it can be modified.

To bookmark HTTP URLs with lynx, put the following line in your lynx.cfg::

```
    EXTERNAL:http:dlcs postit %s
```

For the elinks browser, create a uri\_passing rule in the configuration file.
Something like the following::

```
    set document.uri_passing.dlcs = "bash -c \"dlcs postit %c\""
```