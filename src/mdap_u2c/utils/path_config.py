from mdap_u2c.config.path_config import PathConfig


def getAssetsImagesDir():
    return str(PathConfig.get_root_dir() / "assets" / "images")


def getAssetsSmallModelDir():
    return str(PathConfig.get_root_dir() / "assets" / "small_model")
