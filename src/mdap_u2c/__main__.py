"""主入口：python -m mdap_u2c [--port=PORT]"""

if __name__ == "__main__":
    from mdap_u2c.config import AppConfig
    from mdap_u2c.core import LoggingApplication
    from mdap_u2c.server import run_server

    config = AppConfig.get_instance().CONFIG
    LoggingApplication.init(file_name="run", log_level=config.LOG_LEVEL)
    run_server()
