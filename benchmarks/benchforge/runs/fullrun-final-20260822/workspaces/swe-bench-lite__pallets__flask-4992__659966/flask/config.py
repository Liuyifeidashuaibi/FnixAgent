def from_file(self, filename, load, silent=False, mode="r"):
    """Update the values in the config from a file. The file must
    contain a Python dictionary or other mapping object.

    :param filename: The filename of the config. This can either be an
        absolute filename or a filename relative to the root path.
    :param load: A callable that takes a file handle and returns a
        mapping object. For example, ``json.load`` or ``yaml.safe_load``.
    :param silent: If set to ``True``, no error will be raised if the
        file does not exist.
    :param mode: The file mode to open the file with. Default is "r"
        for text mode. Use "rb" for binary mode (e.g., for TOML files).
    """
    import os

    if filename.startswith(("/", "./", "../")):
        filename = os.path.join(self.root_path, filename)

    try:
        with open(filename, mode) as f:
            obj = load(f)
    except OSError as e:
        if silent:
            return False
        e.strerror = f"Unable to load configuration file ({e.strerror})"
        raise

    if isinstance(obj, dict):
        self.from_mapping(obj)
    else:
        raise ValueError(
            f"Unsupported file type, {type(obj).__name__} returned by load function."
        )
    return True