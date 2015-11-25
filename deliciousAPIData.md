# del.icio.us API #

The version 1 API:
  * supports 12 different calls; 5 to change and 7 to retrieve data
  * does all calls via HTTP GET
  * returns all answers in XML
  * uses XML root elements: posts, tags, bundles, dates, update and result.

The del.icio.us API documention is found at http://del.icio.us/help/api/.
Erreta are given in the details section below.

For a detailed diagram of API paths and result XML see [del.icio.us API @ dotmpe.com](http://www.dotmpe.com/note/del-icio-us)

# Details #
Inconsistencies in structure and between documentation and implementation.

**result**

> The root node `<result/>` sometimes has an attribute called code, otherwise a textnode child representing the result message. posts/delete and posts/add return a `<result code="…"/>`, all other functions return `<result>…</result>`.

**posts/get, posts/all, posts/recent**

> Three functions returning the same XML elements (`<posts><post ...`), but each time with different attributes on the document root node. Only common attribute is user.

**posts/all**

> Returned 

&lt;posts/&gt;

 never has an tag attribute as described in API documentation, not even when filtering on a tag.

**posts/get**

> `dt` argument accepts a full ISO 8601 date (concordant with API help), but the results do not make sense for anything more specific than a date. When filtering using a full ISO 8601 datetime, the `dt` attribute on the `<posts/>` (get) element will reflect the exact passed value however the time attributes of the post elements don't make much sense (shifting as much as a day, API bug?). Filtering on a date seems to work fine (quality is OK, quantity unchecked).