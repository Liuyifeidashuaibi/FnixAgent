import os
from os import path

from sphinx.builders import Builder
from sphinx.util.osutil import ensuredir


class ManualPageBuilder(Builder):
    """
    Builds groff manual pages.
    """
    name = 'man'
    format = 'man'
    epilog = 'The manual pages have been generated in %(outdir)s.'

    def init(self):
        pass

    def get_outdated_docs(self):
        return 'all' if self.env.config.today else 'env'

    def get_target_uri(self, docname, typ=None):
        return ''

    def prepare_writing(self, docnames):
        pass

    def write_doc(self, docname, doctree):
        pass

    def finish(self):
        # type: () -> None
        self.info('writing... ', nonl=True)

        # get path to manpage
        if self.config.man_pages:
            for entry in self.config.man_pages:
                # Extract section number from entry[3] (section) and create section subdirectory
                section = str(entry[3])
                # Ensure section is numeric and create proper section directory
                if section.isdigit():
                    section_dir = path.join(self.outdir, 'man' + section)
                    ensuredir(section_dir)
                    outfilename = path.join(section_dir, entry[0] + '.' + entry[3])
                else:
                    outfilename = path.join(self.outdir, entry[0] + '.' + entry[3])
                
                self.info('writing %s...' % outfilename)
                f = open(outfilename, 'w', encoding='utf-8')
                try:
                    # Generate man page content here
                    # This is simplified - actual implementation would generate the man page
                    f.write('.TH %s "%s" "%s" "%s" "%s"\n' % (
                        entry[0], entry[3], self.config.today, 
                        self.config.project, self.config.release))
                    f.write('.SH NAME\n')
                    f.write('%s \- %s\n' % (entry[0], entry[1]))
                    f.write('.SH DESCRIPTION\n')
                    f.write('%s\n' % entry[2])
                finally:
                    f.close()

        self.info('done')
