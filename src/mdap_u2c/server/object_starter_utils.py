from mdap_u2c.dsl_processors import pipeline

class ObjectStarterUtils:

    @staticmethod
    def run():
        # 提前加载处理器(提高mcp处理速度)
        pipeline.ProcessorPipeline.get_instance()


