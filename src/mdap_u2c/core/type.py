from threading import RLock


class SingletonClass(type):
    single_lock = RLock()

    def __call__(cls, *args, **kwargs):
        with SingletonClass.single_lock:
            if not hasattr(cls, "_instance"):
                cls._instance = super(SingletonClass, cls).__call__(*args, **kwargs)
        return cls._instance
