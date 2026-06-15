import argparse

from .type import SingletonClass


class CliArgs(metaclass=SingletonClass):
    """命令行参数：port。"""

    def __init__(self):
        parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--port", type=int, required=False, default=None, help="端口")

        try:
            parsed = parser.parse_args()
        except SystemExit:
            parsed = argparse.Namespace(port=None)

        self.port = parsed.port

    @staticmethod
    def get_instance():
        return CliArgs()

    def __str__(self):
        attrs = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        attrs_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
        return f"{self.__class__.__name__}({attrs_str})"

    def __repr__(self):
        return self.__str__()
