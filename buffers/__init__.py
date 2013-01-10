try:
    from carray_buffer import Buffer
except ImportError:
    from jericho import Buffer
    
    
__all__ = ['Buffer']