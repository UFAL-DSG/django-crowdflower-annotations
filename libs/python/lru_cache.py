# This module is adapted from Python 3.2's functools' lru_cache.
from modified_collections import OrderedDict
from functools import wraps


def lru_cache(maxsize=100):
    """Least-recently-used cache decorator.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    Arguments to the cached function must be hashable.

    Clear the cache and statistics with f.cache_clear().
    Access the underlying function with f.__wrapped__.

    See:  http://en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used

    """
    # Users should only access the lru_cache through its public API:
    #       cache_clear, and f.__wrapped__
    # The internals of the lru_cache are encapsulated for thread safety and
    # to allow the implementation to change (including a possible C version).

    def decorating_function(user_function, tuple=tuple, sorted=sorted, len=len,
                            KeyError=KeyError):

        kwd_mark = (object(),)          # separates positional and keyword args
        # lock = Lock()                 # needed because OrderedDict isn't
                                        # threadsafe
        # MaK: ...but not available, unfortunately

        if maxsize is None:
            cache = dict()              # simple cache without ordering or size
                                        # limit

            @wraps(user_function)
            def wrapper(*args, **kwds):
                key = args
                if kwds:
                    key += kwd_mark + tuple(sorted(kwds.items()))
                try:
                    result = cache[key]
                    return result
                except KeyError:
                    pass
                result = user_function(*args, **kwds)
                cache[key] = result
                return result
        else:
            cache = OrderedDict()           # ordered least recent to most
                                            # recent
            cache_popitem = cache.popitem
            cache_renew = cache.move_to_end

            @wraps(user_function)
            def wrapper(*args, **kwds):
                key = args
                if kwds:
                    key += kwd_mark + tuple(sorted(kwds.items()))
#                 with lock:
                try:
                    result = cache[key]
                    cache_renew(key)    # record recent use of this key
                    return result
                except KeyError:
                    pass

                result = user_function(*args, **kwds)
#                 with lock:
                cache[key] = result     # record recent use of this key
                if len(cache) > maxsize:
                    cache_popitem(0)    # purge least recently used cache entry

                return result

        def cache_clear():
            """Clear the cache and cache statistics"""
#             with lock:
            cache.clear()

        wrapper.cache_clear = cache_clear
        return wrapper

    return decorating_function

