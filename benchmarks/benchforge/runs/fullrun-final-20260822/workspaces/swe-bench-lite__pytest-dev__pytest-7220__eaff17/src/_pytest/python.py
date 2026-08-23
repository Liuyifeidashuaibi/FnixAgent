class Function:
    def reportinfo(self):
        # Get the file path relative to the original test root directory
        # instead of current working directory to fix path display issues
        # when os.chdir() is used in fixtures
        if hasattr(self, 'config') and self.config and hasattr(self.config, 'rootpath'):
            try:
                relpath = self.fspath.relto(self.config.rootpath)
                return (relpath, self.lineno, self.name)
            except Exception:
                pass
        # Fallback to original behavior
        return (self.fspath, self.lineno, self.name)
